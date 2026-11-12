"""ModelClient backed by OpenRouter's Responses API."""

import asyncio
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from manyminds.core import prompts
from manyminds.core.errors import ModelError
from manyminds.core.models import (
    ErrorKind,
    EvidenceItem,
    JobEventKind,
    Report,
    SearchEngine,
    Usage,
)
from manyminds.core.openrouter import websearch
from manyminds.core.openrouter.schemas import (
    CHAT_SCHEMA,
    DECOMPOSITION_SCHEMA,
    REPORT_SCHEMA,
    WireChatReply,
    WireDecomposition,
    WireReport,
    text_format,
)
from manyminds.core.openrouter.transport import Transport
from manyminds.core.ports import (
    ChatContext,
    ChatReply,
    Decomposition,
    Progress,
    ProgressCallback,
    ResearchResult,
)
from manyminds.core.safety import quote_in_passages, url_key

_Wire = TypeVar("_Wire", bound=BaseModel)
_MAX_PROBLEM_TEXT = 2000
_FINAL_EVENTS = ("response.completed", "response.incomplete")


@dataclass
class _Tally:
    """Usage added up across the calls of one job."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    searches: int = 0

    def add(self, response: dict[str, Any]) -> None:
        usage = response.get("usage")
        if isinstance(usage, dict):
            self.input_tokens += int(_number(usage.get("input_tokens")))
            self.output_tokens += int(_number(usage.get("output_tokens")))
            self.cost += _number(usage.get("cost"))
        self.searches += websearch.search_count(response)

    def usage(self) -> Usage:
        return Usage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cost=self.cost,
            searches=self.searches,
        )


@dataclass
class _Shared:
    """What the links and images in the user's text turned out to show."""

    fetched: list[websearch.Fetch]
    images: list[tuple[str, str | None]]
    """(address, description); the description is None if the image could not be looked at."""

    @property
    def pages(self) -> list[tuple[str, str | None, str | None]]:
        return [(page.url, page.title, page.content) for page in self.fetched]

    def seen(self) -> str:
        """A plain account for the user of what was read."""
        lines = []
        for page in self.fetched:
            if page.content is None:
                lines.append(f"Could not open: {page.url}")
            else:
                lines.append(f"Opened: {page.title or 'Untitled page'} ({page.url})")
        for url, description in self.images:
            lines.append(f"Image {url}: {description or 'could not be looked at'}")
        return "\n".join(lines)


def _fetched(response: dict[str, Any]) -> list[websearch.Fetch]:
    output = response.get("output")
    pages = [
        websearch.fetch_from_item(item) for item in (output if isinstance(output, list) else [])
    ]
    return [page for page in pages if page is not None]


class OpenRouterModelClient:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def decompose(
        self, text: str, instructions: str, *, count: int, avoid: Sequence[str], model: str
    ) -> Decomposition:
        tally = _Tally()
        shared = await self._shared(text, model, tally)
        body = {
            "model": model,
            "instructions": prompts.DECOMPOSE_INSTRUCTIONS,
            "input": prompts.decompose_input(
                text, instructions, count, avoid, shared.pages, shared.images
            ),
        }
        wire = await self._structured(
            body, "decomposition", DECOMPOSITION_SCHEMA, WireDecomposition, tally
        )
        return Decomposition(title=wire.title, leads=wire.leads[:count], seen=shared.seen())

    async def converse(self, message: str, context: ChatContext, *, model: str) -> ChatReply:
        """Answer in the main conversation. The call has no tools; only links the user put
        in this message are opened first."""
        tally = _Tally()
        shared = await self._shared(message, model, tally)
        leads = [
            (
                note.text,
                note.state,
                [
                    prompts.report_lines(
                        report.summary,
                        [
                            (item.stance.value, item.url, item.quote, item.grounded)
                            for item in report.evidence
                        ],
                        report.undetermined,
                    )
                    for report in note.reports
                ],
            )
            for note in context.leads
        ]
        turns = [(turn.role.value, turn.body) for turn in context.turns]
        body = {
            "model": model,
            "instructions": prompts.CHAT_INSTRUCTIONS,
            "input": prompts.chat_input(message, turns, leads, shared.pages, shared.images),
        }
        wire = await self._structured(body, "chat_reply", CHAT_SCHEMA, WireChatReply, tally)
        return ChatReply(body=wire.reply, leads=wire.leads)

    async def _shared(self, text: str, model: str, tally: _Tally) -> _Shared:
        """Work out what the links and images in the user's text show.

        Linked pages are opened; a link that will not open is looked for another way; images,
        whether linked directly or found on those pages, are each shown to the model.
        """
        pages = await self._read_links(text, model, tally)
        failed = [page.url for page in pages if page.content is None]
        if failed:
            pages += await self._read_around(failed, model, tally)
        opened = [page.content for page in pages if page.content is not None]
        urls = prompts.image_links([text, *opened])
        described = await asyncio.gather(*(self._look(url, model, tally) for url in urls))
        return _Shared(pages, list(zip(urls, described, strict=True)))

    async def _read_links(self, text: str, model: str, tally: _Tally) -> list[websearch.Fetch]:
        """Open the pages the text links to.

        The tool is held to the sites the text itself links to, so that nothing on a page can
        send the model on to an address of its own choosing.
        """
        sites = prompts.linked_sites(text)
        if not sites:
            return []
        final = await self._run(
            {
                "model": model,
                "instructions": prompts.READ_INSTRUCTIONS,
                "input": prompts.read_input(text),
                "tools": [
                    websearch.fetch_tool_entry(
                        max_uses=prompts.MAX_LINKED_PAGES, allowed_domains=sites
                    )
                ],
            },
            tally,
        )
        return _fetched(final)[: prompts.MAX_LINKED_PAGES]

    async def _read_around(
        self, links: Sequence[str], model: str, tally: _Tally
    ) -> list[websearch.Fetch]:
        """Look for what unopened links show somewhere else: a mirror, an archive, coverage.

        This call may search and open any site, so it is given the addresses alone and never
        what the user wrote. If it fails, the leads are written without it.
        """
        try:
            final = await self._run(
                {
                    "model": model,
                    "instructions": prompts.READ_AROUND_INSTRUCTIONS,
                    "input": prompts.read_around_input(links),
                    "tools": [
                        websearch.tool_entry(SearchEngine.EXA),
                        websearch.fetch_tool_entry(max_uses=prompts.MAX_LINKED_PAGES),
                    ],
                    **websearch.REQUEST_FIELDS,
                },
                tally,
            )
        except ModelError:
            return []
        found = [page for page in _fetched(final) if page.content is not None]
        return found[: prompts.MAX_LINKED_PAGES]

    async def _look(self, url: str, model: str, tally: _Tally) -> str | None:
        """A description of one image, or None if the model could not be shown it."""
        body = {
            "model": model,
            "instructions": prompts.IMAGE_INSTRUCTIONS,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompts.IMAGE_REQUEST},
                        {"type": "input_image", "image_url": url},
                    ],
                }
            ],
        }
        try:
            described = _text(await self._run(body, tally)).strip()
        except ModelError:
            return None
        return described[: prompts.MAX_IMAGE_DESCRIPTION_CHARS] or None

    async def research(
        self,
        lead: str,
        source_text: str,
        instructions: str,
        *,
        model: str,
        search: SearchEngine,
        on_progress: ProgressCallback,
    ) -> ResearchResult:
        tally = _Tally()
        found = await self._run(
            {
                "model": model,
                "instructions": prompts.SEARCH_INSTRUCTIONS,
                "input": prompts.search_input(lead, source_text, instructions),
                "tools": [websearch.tool_entry(search), websearch.fetch_tool_entry()],
                **websearch.REQUEST_FIELDS,
            },
            tally,
            lambda item: _report_progress(item, on_progress),
        )
        notes = _text(found)
        if not notes.strip():
            raise ModelError(ErrorKind.INVALID_OUTPUT, "The model searched but wrote nothing.")
        cited = websearch.citations(found)

        on_progress(Progress(JobEventKind.WRITING))
        body = {
            "model": model,
            "instructions": prompts.REPORT_INSTRUCTIONS,
            "input": prompts.report_input(
                lead, [(c.url, c.title, c.passages) for c in cited], notes
            ),
        }
        wire = await self._structured(body, "report", REPORT_SCHEMA, WireReport, tally)
        return ResearchResult(report=_grounded(wire, cited), usage=tally.usage())

    async def _structured(
        self,
        body: dict[str, Any],
        name: str,
        schema: dict[str, Any],
        wire_model: type[_Wire],
        tally: _Tally,
    ) -> _Wire:
        """Ask for JSON in a schema with no tools. One repair attempt, then fail."""
        request = {
            **body,
            "text": text_format(name, schema),
            "provider": {"require_parameters": True},
        }
        reply = _structured_text(await self._run(request, tally))
        try:
            return wire_model.model_validate_json(reply)
        except ValidationError as exc:
            problems = str(exc)[:_MAX_PROBLEM_TEXT]
        retry = {**request, "input": prompts.repair_input(body["input"], reply, problems)}
        reply = _structured_text(await self._run(retry, tally))
        try:
            return wire_model.model_validate_json(reply)
        except ValidationError:
            raise ModelError(
                ErrorKind.INVALID_OUTPUT,
                "The model's answer did not match the required format, twice.",
            ) from None

    async def _run(
        self,
        body: dict[str, Any],
        tally: _Tally,
        on_item: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Run one call to its end and return the final response object."""
        final: dict[str, Any] | None = None
        async for event in self._transport.stream(body):
            kind = event.get("type")
            if kind == "response.output_item.done" and on_item is not None:
                item = event.get("item")
                if isinstance(item, dict):
                    on_item(item)
            elif kind in _FINAL_EVENTS and isinstance(event.get("response"), dict):
                final = event["response"]
        if final is None:
            raise ModelError(ErrorKind.PROVIDER, "The reply ended before it was finished.")
        tally.add(final)
        _raise_if_refused_or_cut_short(final)
        return final


def _number(value: object) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return 0.0


def _parts(response: dict[str, Any], kind: str, field: str) -> list[str]:
    output = response.get("output")
    return [
        part[field]
        for item in (output if isinstance(output, list) else [])
        if isinstance(item, dict)
        and item.get("type") == "message"
        and isinstance(item.get("content"), list)
        for part in item["content"]
        if isinstance(part, dict) and part.get("type") == kind and isinstance(part.get(field), str)
    ]


def _text(response: dict[str, Any]) -> str:
    return "\n\n".join(_parts(response, "output_text", "text"))


def _structured_text(response: dict[str, Any]) -> str:
    """The JSON object in a schema reply, taken from its last text part.

    Providers sometimes ignore the schema and wrap the JSON in a sentence or a code fence, so
    the first object that parses is lifted out. Text with no such object is returned as it is,
    to fail validation and be shown to the model in the repair request.
    """
    parts = _parts(response, "output_text", "text")
    text = parts[-1].strip() if parts else ""
    start = text.find("{")
    while start != -1:
        try:
            _, end = json.JSONDecoder().raw_decode(text, start)
        except ValueError:
            start = text.find("{", start + 1)
            continue
        return text[start:end]
    return text


def _raise_if_refused_or_cut_short(response: dict[str, Any]) -> None:
    refusals = _parts(response, "refusal", "refusal")
    if refusals:
        raise ModelError(ErrorKind.REFUSAL, "The model declined: " + " ".join(refusals))
    if response.get("status") != "incomplete":
        return
    details = response.get("incomplete_details")
    reason = details.get("reason") if isinstance(details, dict) else details
    if not isinstance(reason, str) or not reason:
        reason = "unknown reason"
    if reason == "content_filter":
        said = _text(response) or "no explanation given"
        raise ModelError(
            ErrorKind.REFUSAL, f"The provider's content filter stopped the reply: {said}"
        )
    raise ModelError(ErrorKind.PROVIDER, f"The reply was cut short ({reason}).")


def _report_progress(item: dict[str, Any], on_progress: ProgressCallback) -> None:
    kind = item.get("type")
    search = websearch.search_from_item(item)
    if search is not None:
        if search.query:
            on_progress(Progress(JobEventKind.SEARCHING, search.query))
        if search.urls:
            on_progress(Progress(JobEventKind.SOURCES_FOUND, "\n".join(search.urls)))
    elif (fetched := websearch.fetch_from_item(item)) is not None:
        failed = "" if fetched.content is not None else " (could not be opened)"
        on_progress(Progress(JobEventKind.READING, fetched.url + failed))
    elif kind == "reasoning":
        summary = item.get("summary")
        summaries = [
            part["text"]
            for part in (summary if isinstance(summary, list) else [])
            if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"]
        ]
        if summaries:
            on_progress(Progress(JobEventKind.THINKING, "\n\n".join(summaries)))
    elif kind == "message":
        text = _text({"output": [item]})
        if text.strip():
            on_progress(Progress(JobEventKind.MESSAGE, text))


def _grounded(wire: WireReport, cited: Sequence[websearch.Citation]) -> Report:
    """Build the report, flagging each item against what the search tool returned."""
    by_key = {url_key(c.url): c for c in cited}
    evidence = []
    for item in wire.evidence:
        source = by_key.get(url_key(item.url))
        evidence.append(
            EvidenceItem(
                # A grounded item links to the page the search returned, not to whatever
                # variant of its address the model wrote.
                url=source.url if source is not None else item.url,
                title=item.title,
                quote=item.quote,
                stance=item.stance,
                grounded=source is not None,
                quote_matched=(
                    quote_in_passages(item.quote, source.passages) if source is not None else None
                ),
            )
        )
    return Report(summary=wire.summary, evidence=evidence, undetermined=wire.undetermined)
