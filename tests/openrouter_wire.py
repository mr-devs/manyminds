"""A scripted stand-in for OpenRouter's HTTP endpoint, for adapter tests.

Replies are served in order through `httpx.MockTransport`, so the adapter's own HTTP, stream
parsing and error handling all run for real. Event shapes follow the captured fixtures.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).parent / "adapter" / "fixtures"
API_KEY = "sk-or-v1-test-0123456789abcdef-do-not-leak"

Reply = bytes | httpx.Response | Exception


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def sse(*events: dict[str, Any]) -> bytes:
    """A stream body: a keep-alive comment, the events, then the end marker."""
    lines = [": OPENROUTER PROCESSING"]
    lines += ["data: " + json.dumps(event) for event in events]
    lines.append("data: [DONE]")
    return ("\n\n".join(lines) + "\n\n").encode()


def message_item(text: str, annotations: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    return {
        "type": "message",
        "id": "msg-1",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": list(annotations)}],
    }


def search_item(query: str, urls: Sequence[str] = ()) -> dict[str, Any]:
    action: dict[str, Any] = {"type": "search", "query": query}
    if urls:
        action["sources"] = [{"type": "url", "url": url} for url in urls]
    return {"type": "openrouter:web_search", "id": "st-1", "status": "completed", "action": action}


def fetch_item(
    url: str, title: str | None = None, content: str | None = None, error: str | None = None
) -> dict[str, Any]:
    """A page the model opened, shaped like the captured `openrouter:web_fetch` items."""
    item: dict[str, Any] = {"type": "openrouter:web_fetch", "id": "st-2", "url": url}
    if error is not None:
        return {**item, "status": "incomplete", "error": error}
    return {**item, "status": "completed", "httpStatus": 200, "title": title, "content": content}


def reasoning_item(*summaries: str) -> dict[str, Any]:
    return {
        "type": "reasoning",
        "id": "rs-1",
        "status": "completed",
        "summary": [{"type": "summary_text", "text": text} for text in summaries],
        "encrypted_content": "REDACTED",
    }


def citation(url: str, title: str, excerpt: str | None = None) -> dict[str, Any]:
    annotation: dict[str, Any] = {
        "type": "url_citation",
        "url": url,
        "title": title,
        "start_index": 0,
        "end_index": 0,
    }
    if excerpt is not None:
        annotation["content"] = excerpt
    return annotation


def stream_of(
    *items: dict[str, Any],
    status: str = "completed",
    incomplete_reason: str | None = None,
    usage: dict[str, Any] | None = None,
) -> bytes:
    """A whole stream that delivers the given output items and then finishes."""
    events: list[dict[str, Any]] = [
        {"type": "response.created", "response": {"status": "in_progress"}}
    ]
    for index, item in enumerate(items):
        events.append({"type": "response.output_item.done", "output_index": index, "item": item})
    response = {
        "id": "gen-1",
        "object": "response",
        "status": status,
        "error": None,
        "incomplete_details": {"reason": incomplete_reason} if incomplete_reason else None,
        "output": list(items),
        "usage": usage or {"input_tokens": 100, "output_tokens": 50, "cost": 0.001},
    }
    events.append({"type": f"response.{status}", "response": response})
    return sse(*events)


def json_reply(value: Any, **kwargs: Any) -> bytes:
    """A stream whose only output is the given value as JSON text."""
    return stream_of(message_item(json.dumps(value)), **kwargs)


def text_reply(text: str, **kwargs: Any) -> bytes:
    return stream_of(message_item(text), **kwargs)


def error_response(
    status: int, message: str = "upstream said no", **headers: str
) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"code": status, "message": message}}, headers=headers
    )


class Wire:
    """Serves scripted replies and records every request made."""

    def __init__(self, *replies: Reply) -> None:
        self._replies = list(replies)
        self.requests: list[httpx.Request] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._replies:
            raise AssertionError(f"unexpected request number {len(self.requests)}")
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx.Response):
            return reply
        return httpx.Response(200, content=reply, headers={"content-type": "text/event-stream"})

    def http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))

    @property
    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(request.content) for request in self.requests]
