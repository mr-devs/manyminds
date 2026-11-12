"""Behaviour pinned after the second review of milestone 1b."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind, JobEventKind, SearchEngine
from manyminds.core.openrouter.adapter import OpenRouterModelClient
from manyminds.core.openrouter.client import build_client
from manyminds.core.openrouter.transport import Transport
from manyminds.core.ports import Progress, ResearchResult
from manyminds.core.safety import quote_in_passages
from openrouter_wire import (
    API_KEY,
    Wire,
    citation,
    json_reply,
    message_item,
    search_item,
    sse,
    stream_of,
    text_reply,
)

PAGE = "https://a.example/page"
EXCERPT = "The bridge opened to traffic in March 1932 after six years of work."


def report(quote: str = "opened to traffic in March 1932", url: str = PAGE) -> dict[str, Any]:
    return {
        "summary": "One page was found.",
        "evidence": [{"url": url, "title": "A page", "quote": quote, "stance": "supports"}],
        "undetermined": "Everything else.",
    }


def search_reply(*annotations: dict[str, Any]) -> bytes:
    cited = annotations or (citation(PAGE, "A page", EXCERPT),)
    return stream_of(search_item("a query", [PAGE]), message_item("Notes.", cited))


async def research(wire: Wire, progress: list[Progress] | None = None) -> ResearchResult:
    seen = progress if progress is not None else []
    async with wire.http() as http:
        client = OpenRouterModelClient(Transport(API_KEY, http))
        return await client.research(
            "A lead.",
            "Some pasted text.",
            "",
            model="vendor/model-a",
            search=SearchEngine.EXA,
            on_progress=seen.append,
        )


async def events_of(body: bytes) -> list[dict[str, Any]]:
    wire = Wire(body)
    async with wire.http() as http:
        return [event async for event in Transport(API_KEY, http).stream({"model": "m"})]


async def transport_failure(reply: Any) -> ModelError:
    with pytest.raises(ModelError) as caught:
        await events_of(reply)
    return caught.value


# -- stream framing -----------------------------------------------------------------------


@pytest.mark.parametrize("separator", [chr(0x2028), chr(0x2029), chr(0x85)])
async def test_unusual_line_characters_inside_an_event_do_not_split_it(separator: str) -> None:
    text = f"before{separator}after"
    line = 'data: {"type": "response.created", "note": "' + text + '"}'
    body = (line + "\n\ndata: [DONE]\n\n").encode()

    events = await events_of(body)

    assert events == [{"type": "response.created", "note": text}]


# -- quote checking -----------------------------------------------------------------------


async def test_a_quote_copied_with_the_prompts_escaping_still_matches() -> None:
    search = search_reply(
        citation(PAGE, "A page", "The effect was significant (p < 0.05) in both trials.")
    )
    wire = Wire(search, json_reply(report("significant (p &lt; 0.05) in both trials")))

    result = await research(wire)

    assert "(p &lt; 0.05)" in wire.bodies[1]["input"]
    assert result.report.evidence[0].quote_matched is True


def test_a_quote_containing_an_inline_ellipsis_marker_matches_verbatim() -> None:
    passage = "The bridge opened [...] to traffic in March 1932."

    assert quote_in_passages("opened [...] to traffic in March 1932", (passage,)) is True


def test_a_quote_cannot_span_the_divider_exa_puts_between_passages() -> None:
    excerpt = "The wall was never visible\n\n...\n\nfrom the Moon with the naked eye."

    assert (
        quote_in_passages("was never visible ... from the Moon with the naked eye", (excerpt,))
        is False
    )
    assert quote_in_passages("from the Moon with the naked eye", (excerpt,)) is True


def test_a_bracketed_divider_on_its_own_line_also_separates_passages() -> None:
    excerpt = "The wall was never visible\n[...]\nfrom the Moon with the naked eye."

    assert (
        quote_in_passages("was never visible from the Moon with the naked eye", (excerpt,)) is False
    )


async def test_a_short_verbatim_quote_is_unchecked_not_flagged() -> None:
    search = search_reply(citation(PAGE, "A page", "The wall is 21,196 km long, the survey says."))

    result = await research(Wire(search, json_reply(report("21,196 km long"))))

    assert result.report.evidence[0].grounded is True
    assert result.report.evidence[0].quote_matched is None


# -- the report call is not given the same text twice ------------------------------------


async def test_a_page_cited_repeatedly_appears_once_in_the_report_request() -> None:
    search = stream_of(
        search_item("first", [PAGE]),
        search_item("second", [f"{PAGE}?utm_source=openai"]),
        message_item(
            "Notes.",
            [
                citation(PAGE, "A page", EXCERPT),
                citation(PAGE, "A page", EXCERPT),
                citation(f"{PAGE}?utm_source=openai", "A page", EXCERPT),
            ],
        ),
    )
    wire = Wire(search, json_reply(report()))

    result = await research(wire)

    given = wire.bodies[1]["input"]
    assert given.count("<source ") == 1
    assert given.count(EXCERPT) == 1
    assert result.report.evidence[0].quote_matched is True
    assert result.report.evidence[0].url == PAGE


# -- odd shapes ---------------------------------------------------------------------------


async def test_incomplete_details_that_is_not_an_object_is_still_a_cut_short_reply() -> None:
    final = {
        "status": "incomplete",
        "incomplete_details": "max_output_tokens",
        "output": [message_item("partial")],
    }

    with pytest.raises(ModelError) as caught:
        await research(Wire(sse({"type": "response.incomplete", "response": final})))

    assert caught.value.kind is ErrorKind.PROVIDER


async def test_a_reasoning_item_with_an_odd_summary_is_skipped() -> None:
    search = stream_of(
        {"type": "reasoning", "summary": 5},
        {"type": "reasoning", "summary": [None, "text", {"type": "summary_text", "text": 7}]},
        search_item("a query", [PAGE]),
        message_item("Notes.", [citation(PAGE, "A page", EXCERPT)]),
    )
    progress: list[Progress] = []

    await research(Wire(search, json_reply(report())), progress)

    assert JobEventKind.THINKING not in [p.kind for p in progress]


# -- error codes --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("event", "kind"),
    [
        ({"type": "error", "code": "context_length_exceeded", "message": "m"}, ErrorKind.UNKNOWN),
        ({"type": "error", "code": "invalid_request_error", "message": "m"}, ErrorKind.UNKNOWN),
        (
            {
                "type": "response.failed",
                "response": {"error": {"code": "content_policy_violation"}},
            },
            ErrorKind.REFUSAL,
        ),
        ({"type": "error", "code": "content_filter", "message": "m"}, ErrorKind.REFUSAL),
        ({"type": "error", "code": "server_error", "message": "m"}, ErrorKind.PROVIDER),
        ({"error": {"code": 502, "message": "upstream down"}}, ErrorKind.PROVIDER),
        ({"error": {"code": 429, "message": "slow"}}, ErrorKind.RATE_LIMIT),
    ],
)
async def test_error_codes_decide_the_kind(event: dict[str, Any], kind: ErrorKind) -> None:
    error = await transport_failure(sse(event))

    assert error.kind is kind


async def test_an_untyped_chunk_carrying_an_error_keeps_its_message() -> None:
    error = await transport_failure(sse({"error": {"code": 502, "message": "upstream down"}}))

    assert "upstream down" in error.message


async def test_an_error_without_an_http_status_does_not_claim_one() -> None:
    body_error = await transport_failure(
        httpx.Response(200, json={"error": {"message": "something broke"}})
    )
    stream_error = await transport_failure(sse({"type": "error", "message": "something broke"}))

    assert "HTTP" not in body_error.message
    assert "HTTP" not in stream_error.message
    assert "something broke" in body_error.message


# -- reading the structured reply ---------------------------------------------------------


@pytest.mark.parametrize(
    "wrapping",
    [
        "Here is the report:\n```json\n{}\n```",
        "```JSON\n{}\n```",
        "```\n{}\n```\nLet me know if you need anything else.",
        "Sure. {} That is everything.",
    ],
)
async def test_json_with_text_around_it_is_read_without_a_repair_call(wrapping: str) -> None:
    reply = wrapping.replace("{}", json.dumps(report()))
    wire = Wire(search_reply(), text_reply(reply))

    result = await research(wire)

    assert result.report.summary == "One page was found."
    assert len(wire.bodies) == 2


async def test_text_with_no_json_object_still_goes_to_repair() -> None:
    wire = Wire(search_reply(), text_reply("No braces here."), json_reply(report()))

    await research(wire)

    assert len(wire.bodies) == 3
    assert "No braces here." in wire.bodies[2]["input"]


# -- one place builds the client -----------------------------------------------------------


async def test_build_client_gives_a_ready_client_with_a_long_read_timeout() -> None:
    client, http = build_client(API_KEY)

    assert isinstance(client, OpenRouterModelClient)
    assert http.timeout == httpx.Timeout(120.0, connect=10.0)
    assert API_KEY not in repr(client) + repr(vars(client))
    await http.aclose()
