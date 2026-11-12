"""The one place an OpenRouter-backed model client is put together."""

import httpx

from manyminds.core.openrouter.adapter import OpenRouterModelClient
from manyminds.core.openrouter.transport import Transport

# A long read timeout: a search call can go quiet for a while between stream events.
TIMEOUT = httpx.Timeout(120.0, connect=10.0)


def build_client(api_key: str) -> tuple[OpenRouterModelClient, httpx.AsyncClient]:
    """A model client for the given key, and the HTTP client under it for the caller to close."""
    http = httpx.AsyncClient(timeout=TIMEOUT)
    return OpenRouterModelClient(Transport(api_key, http)), http
