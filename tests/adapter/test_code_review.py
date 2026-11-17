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
from manyminds.core.ports import Decomposition, Progress, ResearchResult
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


LEADS = {"title": "One page was found.", "leads": ["A lead."]}


async def leads_from(wire: Wire) -> Decomposition:
    async with wire.http() as http:
        client = OpenRouterModelClient(Transport(API_KEY, http))
        return await client.decompose("Some text.", "", count=5, avoid=[], model="vendor/model-b")


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

    await research(Wire(search), progress)

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
    reply = wrapping.replace("{}", json.dumps(LEADS))
    wire = Wire(text_reply(reply))

    result = await leads_from(wire)

    assert result.title == "One page was found."
    assert len(wire.bodies) == 1


async def test_text_with_no_json_object_still_goes_to_repair() -> None:
    wire = Wire(text_reply("No braces here."), json_reply(LEADS))

    await leads_from(wire)

    assert len(wire.bodies) == 2
    assert "No braces here." in wire.bodies[1]["input"]


# -- one place builds the client -----------------------------------------------------------


async def test_build_client_gives_a_ready_client_with_a_long_read_timeout() -> None:
    client, http = build_client(API_KEY)

    assert isinstance(client, OpenRouterModelClient)
    assert http.timeout == httpx.Timeout(120.0, connect=10.0)
    assert API_KEY not in repr(client) + repr(vars(client))
    await http.aclose()
