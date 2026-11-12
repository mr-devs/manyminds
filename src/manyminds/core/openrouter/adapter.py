"""ModelClient backed by OpenRouter's Responses API."""

import math
import re
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
    DECOMPOSITION_SCHEMA,
    REPORT_SCHEMA,
    WireDecomposition,
    WireReport,
    text_format,
)
from manyminds.core.openrouter.transport import Transport
from manyminds.core.ports import Decomposition, Progress, ProgressCallback, ResearchResult
from manyminds.core.safety import quote_in_excerpt, url_key

_Wire = TypeVar("_Wire", bound=BaseModel)
_MAX_PROBLEM_TEXT = 2000
_FINAL_EVENTS = ("response.completed", "response.incomplete")
_FENCED = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


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


class OpenRouterModelClient:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def decompose(
        self, text: str, instructions: str, *, count: int, avoid: Sequence[str], model: str
    ) -> Decomposition:
        body = {
            "model": model,
            "instructions": prompts.DECOMPOSE_INSTRUCTIONS,
            "input": prompts.decompose_input(text, instructions, count, avoid),
        }
        wire = await self._structured(
            body, "decomposition", DECOMPOSITION_SCHEMA, WireDecomposition, _Tally()
        )
        return Decomposition(title=wire.title, leads=wire.leads[:count])

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
                "tools": [websearch.tool_entry(search)],
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
                lead, [(c.url, c.title, c.excerpt) for c in cited], notes
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
    """The JSON of a schema reply: its last text part, without any code fence around it."""
    parts = _parts(response, "output_text", "text")
    text = parts[-1].strip() if parts else ""
    fenced = _FENCED.fullmatch(text)
    return fenced.group(1) if fenced else text


def _raise_if_refused_or_cut_short(response: dict[str, Any]) -> None:
    refusals = _parts(response, "refusal", "refusal")
    if refusals:
        raise ModelError(ErrorKind.REFUSAL, "The model declined: " + " ".join(refusals))
    if response.get("status") != "incomplete":
        return
    reason = (response.get("incomplete_details") or {}).get("reason") or "unknown reason"
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
    elif kind == "reasoning":
        summaries = [
            part["text"]
            for part in item.get("summary") or []
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
    by_key: dict[str, websearch.Citation] = {}
    for citation in cited:
        try:
            key = url_key(citation.url)
        except ValueError:
            continue
        known = by_key.get(key)
        by_key[key] = (
            citation
            if known is None
            else websearch.Citation(
                known.url,
                known.title or citation.title,
                websearch.join_excerpts(known.excerpt, citation.excerpt),
            )
        )
    evidence = []
    for item in wire.evidence:
        source = by_key.get(url_key(item.url))
        matched = (
            quote_in_excerpt(item.quote, source.excerpt)
            if source is not None and source.excerpt
            else None
        )
        evidence.append(
            EvidenceItem(
                # A grounded item links to the page the search returned, not to whatever
                # variant of its address the model wrote.
                url=source.url if source is not None else item.url,
                title=item.title,
                quote=item.quote,
                stance=item.stance,
                grounded=source is not None,
                quote_matched=matched,
            )
        )
    return Report(summary=wire.summary, evidence=evidence, undetermined=wire.undetermined)
