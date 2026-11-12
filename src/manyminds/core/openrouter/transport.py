"""HTTP to OpenRouter: one streamed request, parsed into events, with failures named."""

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind

RESPONSES_URL = "https://openrouter.ai/api/v1/responses"
APP_TITLE = "manyminds"
APP_URL = "https://github.com/mr-devs/manyminds"

_STATUS_KINDS = {
    401: ErrorKind.AUTH,
    402: ErrorKind.CREDITS,
    403: ErrorKind.REFUSAL,
    408: ErrorKind.TIMEOUT,
    429: ErrorKind.RATE_LIMIT,
}


class Transport:
    """Sends a request body to the Responses endpoint and yields its stream events.

    The API key is held in a closure, not an attribute, so it cannot appear in `repr`,
    `vars` or a logged object. Upstream error text has the key removed before it is used.
    """

    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self._client = client
        self._headers: Callable[[], dict[str, str]] = lambda: {
            "Authorization": f"Bearer {api_key}",
            "X-OpenRouter-Title": APP_TITLE,
            "HTTP-Referer": APP_URL,
        }
        self._redact: Callable[[str], str] = lambda text: text.replace(api_key, "[redacted]")

    def __repr__(self) -> str:
        return "Transport(api_key=<hidden>)"

    async def stream(self, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Yield each event of the response. Raises ModelError on any failure."""
        request = {**body, "stream": True}
        try:
            async with self._client.stream(
                "POST", RESPONSES_URL, json=request, headers=self._headers()
            ) as response:
                if response.status_code != 200:
                    raise self._http_error(response, await response.aread())
                if "application/json" in response.headers.get("content-type", ""):
                    raise self._json_instead_of_stream(await response.aread())
                async for line in response.aiter_lines():
                    event = _parse_line(line)
                    if event is None:
                        continue
                    self._raise_if_error(event)
                    yield event
        except httpx.TimeoutException:
            raise ModelError(ErrorKind.TIMEOUT, "The request to OpenRouter timed out.") from None
        except httpx.HTTPError as exc:
            raise ModelError(
                ErrorKind.PROVIDER, f"Could not reach OpenRouter ({type(exc).__name__})."
            ) from None

    def _http_error(self, response: httpx.Response, raw: bytes) -> ModelError:
        return self._error(response.status_code, _upstream_message(raw), _retry_after(response))

    def _json_instead_of_stream(self, raw: bytes) -> ModelError:
        try:
            error = json.loads(raw).get("error")
        except (ValueError, AttributeError):
            error = None
        if not isinstance(error, dict):
            return ModelError(ErrorKind.PROVIDER, "OpenRouter sent an unexpected reply.")
        code = error.get("code")
        return self._error(code if isinstance(code, int) else 500, str(error.get("message", "")))

    def _error(self, status: int, upstream: str, retry_after: float | None = None) -> ModelError:
        detail = self._redact(upstream)
        kind = _STATUS_KINDS.get(status)
        if kind is ErrorKind.AUTH:
            message = "OpenRouter rejected the API key."
        elif kind is ErrorKind.CREDITS:
            message = "The OpenRouter account does not have enough credits."
        elif kind is ErrorKind.REFUSAL:
            message = f"OpenRouter blocked this request: {detail or 'no reason given'}"
        elif kind is ErrorKind.TIMEOUT:
            message = "The request to OpenRouter timed out."
        elif kind is ErrorKind.RATE_LIMIT:
            message = "OpenRouter is limiting requests right now."
        elif status >= 500:
            kind = ErrorKind.PROVIDER
            message = f"The model provider failed (HTTP {status}): {detail or 'no details'}"
        else:
            kind = ErrorKind.UNKNOWN
            message = f"OpenRouter returned an error (HTTP {status}): {detail or 'no details'}"
        return ModelError(kind, message, retry_after=retry_after)

    def _raise_if_error(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "error":
            detail = str(event.get("message", ""))
        elif kind == "response.failed":
            error = (event.get("response") or {}).get("error") or {}
            detail = str(error.get("message", ""))
        else:
            return
        raise ModelError(
            ErrorKind.PROVIDER,
            f"The model provider failed part-way: {self._redact(detail) or 'no details'}",
        )


def _parse_line(line: str) -> dict[str, Any] | None:
    """One stream line as an event, or None for comments, blanks and the end marker."""
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        event = json.loads(payload)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None


def _upstream_message(raw: bytes) -> str:
    try:
        error = json.loads(raw)["error"]
        return str(error["message"])
    except (ValueError, KeyError, TypeError):
        return ""


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return float(response.headers["retry-after"])
    except (KeyError, ValueError):
        return None
