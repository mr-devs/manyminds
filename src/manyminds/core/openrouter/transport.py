"""HTTP to OpenRouter: one streamed request, parsed into events, with failures named."""

import json
import math
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
                async for line in _lines(response):
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
        status = response.status_code
        return self._error(status, _upstream_message(raw), f"HTTP {status}", _retry_after(response))

    def _json_instead_of_stream(self, raw: bytes) -> ModelError:
        try:
            found = _error_details(json.loads(raw))
        except ValueError:
            found = None
        if found is None:
            return ModelError(ErrorKind.PROVIDER, "OpenRouter sent an unexpected reply.")
        return self._error(_status_for(found[0]), found[1], "in its reply")

    def _error(
        self, status: int, upstream: str, where: str, retry_after: float | None = None
    ) -> ModelError:
        """Name a failure. `where` says how it reached us, for the message only."""
        detail = self._redact(upstream) or "no details"
        kind = _STATUS_KINDS.get(status)
        if kind is ErrorKind.AUTH:
            message = "OpenRouter rejected the API key."
        elif kind is ErrorKind.CREDITS:
            message = "The OpenRouter account does not have enough credits."
        elif kind is ErrorKind.REFUSAL:
            message = f"OpenRouter blocked this request: {detail}"
        elif kind is ErrorKind.TIMEOUT:
            message = "The request to OpenRouter timed out."
        elif kind is ErrorKind.RATE_LIMIT:
            message = "OpenRouter is limiting requests right now."
        elif status >= 500:
            kind = ErrorKind.PROVIDER
            message = f"The model provider failed ({where}): {detail}"
        else:
            kind = ErrorKind.UNKNOWN
            message = f"OpenRouter returned an error ({where}): {detail}"
        return ModelError(kind, message, retry_after=retry_after)

    def _raise_if_error(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "error":
            found = _error_details(event) or (event.get("code"), str(event.get("message") or ""))
        elif kind == "response.failed":
            found = _error_details(event.get("response")) or (None, "")
        elif kind is None:
            # Some providers send a bare chunk that holds only an error.
            untyped = _error_details(event)
            if untyped is None:
                return
            found = untyped
        else:
            return
        raise self._error(_status_for(found[0]), found[1], "part-way through the reply")


# Named error codes, as the HTTP status that means the same thing. A name not listed here
# is treated as a problem with the request (400), not as a provider outage: retrying an
# unknown failure would bill the user again for something that may never succeed.
_CODE_STATUS = {
    "invalid_api_key": 401,
    "insufficient_quota": 402,
    "insufficient_credits": 402,
    "content_policy_violation": 403,
    "content_filter": 403,
    "moderation": 403,
    "timeout": 408,
    "rate_limit_exceeded": 429,
    "server_error": 500,
    "internal_error": 500,
    "provider_unavailable": 503,
    "overloaded": 503,
}


def _error_details(holder: object) -> tuple[object, str] | None:
    """The (code, message) of the `error` entry inside a reply, whatever shape it has."""
    if not isinstance(holder, dict) or holder.get("error") is None:
        return None
    error = holder["error"]
    if isinstance(error, dict):
        return error.get("code"), str(error.get("message") or "")
    return None, str(error)


def _status_for(code: object) -> int:
    """An HTTP-style status for an error code that may be a number or a name."""
    if isinstance(code, int) and not isinstance(code, bool):
        return code
    if isinstance(code, str):
        if code.isdigit():
            return int(code)
        return _CODE_STATUS.get(code, 400)
    return 500


async def _lines(response: httpx.Response) -> AsyncIterator[str]:
    """The lines of a stream, split on line feeds only.

    httpx's own line iterator also splits on characters such as U+2028, which may appear
    raw inside an event's JSON text and would cut the event in two.
    """
    pending = ""
    async for chunk in response.aiter_text():
        *lines, pending = (pending + chunk).split("\n")
        for line in lines:
            yield line.rstrip("\r")
    if pending:
        yield pending.rstrip("\r")


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
        seconds = float(response.headers["retry-after"])
    except (KeyError, ValueError):
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None
