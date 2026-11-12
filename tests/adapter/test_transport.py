"""The HTTP layer: request shape, stream parsing, and turning failures into ModelError."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind
from manyminds.core.openrouter.transport import Transport
from openrouter_wire import API_KEY, Wire, error_response, fixture, sse


async def collect(wire: Wire, body: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    async with wire.http() as http:
        transport = Transport(API_KEY, http)
        return [event async for event in transport.stream(body or {"model": "vendor/model-a"})]


async def failure(wire: Wire) -> ModelError:
    with pytest.raises(ModelError) as caught:
        await collect(wire)
    return caught.value


async def test_posts_to_the_responses_endpoint_with_the_key_and_app_headers() -> None:
    wire = Wire(fixture("schema_only.sse"))

    await collect(wire, {"model": "vendor/model-a", "input": "hello"})

    request = wire.requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://openrouter.ai/api/v1/responses"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert request.headers["x-openrouter-title"] == "manyminds"
    assert request.headers["http-referer"] == "https://github.com/mr-devs/manyminds"
    assert wire.bodies[0] == {"model": "vendor/model-a", "input": "hello", "stream": True}


async def test_yields_each_event_and_drops_comments_and_the_end_marker() -> None:
    events = await collect(Wire(fixture("schema_only.sse")))

    assert len(events) == 11
    assert events[0]["type"] == "response.created"
    assert events[-1]["type"] == "response.completed"
    assert events[-1]["response"]["usage"]["cost"] == 0.000267


async def test_an_event_split_across_network_chunks_is_still_parsed() -> None:
    body = sse({"type": "response.created", "response": {"status": "in_progress"}})
    half = len(body) // 2

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=iter([body[:half], body[half:]]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        events = [event async for event in Transport(API_KEY, http).stream({"model": "m"})]

    assert events == [{"type": "response.created", "response": {"status": "in_progress"}}]


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (400, ErrorKind.UNKNOWN),
        (401, ErrorKind.AUTH),
        (402, ErrorKind.CREDITS),
        (403, ErrorKind.REFUSAL),
        (408, ErrorKind.TIMEOUT),
        (429, ErrorKind.RATE_LIMIT),
        (500, ErrorKind.PROVIDER),
        (502, ErrorKind.PROVIDER),
        (503, ErrorKind.PROVIDER),
    ],
)
async def test_http_errors_map_to_error_kinds(status: int, kind: ErrorKind) -> None:
    error = await failure(Wire(error_response(status)))

    assert error.kind is kind
    assert error.message


async def test_rate_limit_carries_the_retry_after_header() -> None:
    error = await failure(Wire(error_response(429, **{"Retry-After": "7"})))

    assert error.retry_after == 7.0


async def test_retry_after_is_absent_when_the_header_is_missing_or_not_a_number() -> None:
    missing = await failure(Wire(error_response(429)))
    odd = await failure(Wire(error_response(429, **{"Retry-After": "soon"})))

    assert missing.retry_after is None
    assert odd.retry_after is None


async def test_an_error_page_that_is_not_json_is_still_a_provider_error() -> None:
    error = await failure(Wire(httpx.Response(502, text="<html>Bad Gateway</html>")))

    assert error.kind is ErrorKind.PROVIDER


async def test_a_moderation_block_shows_the_reason_openrouter_gave() -> None:
    error = await failure(Wire(error_response(403, "Input flagged for violence")))

    assert error.kind is ErrorKind.REFUSAL
    assert "Input flagged for violence" in error.message


async def test_an_error_body_sent_with_http_200_is_an_error() -> None:
    reply = httpx.Response(200, json={"error": {"code": 429, "message": "slow down"}})

    error = await failure(Wire(reply))

    assert error.kind is ErrorKind.RATE_LIMIT


async def test_a_response_failed_event_mid_stream_is_a_provider_error() -> None:
    failed = {
        "type": "response.failed",
        "response": {
            "status": "failed",
            "output": [],
            "error": {"code": "server_error", "message": "Provider disconnected unexpectedly"},
        },
    }
    body = sse({"type": "response.created", "response": {"status": "in_progress"}}, failed)

    error = await failure(Wire(body))

    assert error.kind is ErrorKind.PROVIDER
    assert "Provider disconnected unexpectedly" in error.message


async def test_a_bare_error_event_mid_stream_is_a_provider_error() -> None:
    body = sse({"type": "error", "code": "server_error", "message": "upstream went away"})

    error = await failure(Wire(body))

    assert error.kind is ErrorKind.PROVIDER


async def test_a_timeout_is_a_timeout_error() -> None:
    error = await failure(Wire(httpx.ReadTimeout("timed out")))

    assert error.kind is ErrorKind.TIMEOUT


async def test_a_failed_connection_is_a_provider_error() -> None:
    error = await failure(Wire(httpx.ConnectError("no route to host")))

    assert error.kind is ErrorKind.PROVIDER


@pytest.mark.parametrize(
    "reply",
    [
        error_response(401, f"No auth for key {API_KEY}"),
        error_response(500),
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("refused"),
        sse({"type": "error", "message": f"bad key {API_KEY}"}),
    ],
)
async def test_the_api_key_never_reaches_errors_logs_or_repr(
    reply: Any, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    wire = Wire(reply)
    async with wire.http() as http:
        transport = Transport(API_KEY, http)
        with pytest.raises(ModelError) as caught:
            async for _ in transport.stream({"model": "m"}):
                pass

    error = caught.value
    leaks = [
        str(error),
        repr(error),
        error.message,
        repr(transport),
        str(vars(transport)),
        caplog.text,
    ]
    assert all(API_KEY not in text for text in leaks)
    assert error.__cause__ is None or API_KEY not in repr(error.__cause__)
