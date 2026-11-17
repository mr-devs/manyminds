"""The only module that knows the shapes of OpenRouter's web tools.

Built against the beta documentation as of 2026-11-12.

`openrouter:web_search`: non-native engines (Exa) return each result as a `url_citation`
annotation with an excerpt. Provider-native search returns only a list of URLs on the search
item, and only when the request asks for it with `include`.

`openrouter:web_fetch`: opens one page and returns its text on an output item. The Exa engine
is always used, because it returns extracted text (for a YouTube link, the transcript) where
a plain HTTP fetch returns the page's markup.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from manyminds.core.models import SearchEngine
from manyminds.core.safety import url_key

MAX_RESULTS_PER_SEARCH = 5
MAX_SEARCHES = 6
MAX_FETCHES = 6
MAX_PAGE_TOKENS = 8000
_SEARCH_ITEM_TYPES = ("openrouter:web_search", "web_search_call")
_FETCH_ITEM_TYPE = "openrouter:web_fetch"

REQUEST_FIELDS: dict[str, Any] = {"include": ["web_search_call.action.sources"]}
"""Extra top-level request fields a search call needs."""


@dataclass(frozen=True)
class Citation:
    """One page the search tool returned."""

    url: str
    title: str | None
    passages: tuple[str, ...]
    """Excerpts of the page, each a separate piece of its text. Empty when none came back."""


@dataclass(frozen=True)
class Search:
    """One search the model ran."""

    query: str
    urls: tuple[str, ...]


@dataclass(frozen=True)
class Fetch:
    """One page the model opened, or tried to."""

    url: str
    title: str | None
    content: str | None
    error: str | None


def fetch_tool_entry(
    *, max_uses: int = MAX_FETCHES, allowed_domains: Sequence[str] | None = None
) -> dict[str, Any]:
    """The tool that opens a page. `allowed_domains` limits it to the named sites."""
    parameters: dict[str, Any] = {
        "engine": "exa",
        "max_uses": max_uses,
        "max_content_tokens": MAX_PAGE_TOKENS,
    }
    if allowed_domains is not None:
        parameters["allowed_domains"] = list(allowed_domains)
    return {"type": _FETCH_ITEM_TYPE, "parameters": parameters}


def fetch_from_item(item: object) -> Fetch | None:
    """The page an output item says was opened, or None if the item is not a fetch."""
    if not isinstance(item, dict) or item.get("type") != _FETCH_ITEM_TYPE:
        return None
    url = item.get("url")
    if not isinstance(url, str) or not url:
        return None
    content, title, error = item.get("content"), item.get("title"), item.get("error")
    if isinstance(content, str) and content:
        return Fetch(url, title if isinstance(title, str) and title else None, content, None)
    return Fetch(url, None, None, error if isinstance(error, str) and error else "no content")


def tool_entry(engine: SearchEngine) -> dict[str, Any]:
    return {
        "type": "openrouter:web_search",
        "parameters": {
            "engine": engine.value,
            "max_results": MAX_RESULTS_PER_SEARCH,
            "max_uses": MAX_SEARCHES,
        },
    }


def search_from_item(item: object) -> Search | None:
    """The search an output item describes, or None if the item is not a search."""
    if not isinstance(item, dict) or item.get("type") not in _SEARCH_ITEM_TYPES:
        return None
    action = item.get("action")
    if not isinstance(action, dict):
        return Search("", ())
    sources = action.get("sources")
    urls = tuple(
        source["url"]
        for source in (sources if isinstance(sources, list) else [])
        if isinstance(source, dict) and isinstance(source.get("url"), str)
    )
    query = action.get("query")
    return Search(query if isinstance(query, str) else "", urls)


def _annotations(item: object) -> list[dict[str, Any]]:
    if not isinstance(item, dict) or not isinstance(item.get("content"), list):
        return []
    return [
        annotation
        for part in item["content"]
        if isinstance(part, dict) and isinstance(part.get("annotations"), list)
        for annotation in part["annotations"]
        if isinstance(annotation, dict)
        and annotation.get("type") == "url_citation"
        and isinstance(annotation.get("url"), str)
    ]


def _output(response: dict[str, Any]) -> list[object]:
    output = response.get("output")
    return output if isinstance(output, list) else []


def citations(response: dict[str, Any]) -> list[Citation]:
    """Every page the search returned in this response, one entry per page, in order.

    Two addresses that differ only in tracking parameters are one page. It keeps the first
    address seen, and each distinct excerpt once.
    """
    found: dict[str, Citation] = {}

    def add(url: str, title: object, passage: object) -> None:
        try:
            key = url_key(url)
        except ValueError:
            return
        known = found.get(key) or Citation(url, None, ())
        passages = known.passages
        if isinstance(passage, str) and passage and passage not in passages:
            passages = (*passages, passage)
        named = title if isinstance(title, str) and title else None
        found[key] = Citation(known.url, known.title or named, passages)

    for item in _output(response):
        search = search_from_item(item)
        if search is not None:
            for url in search.urls:
                add(url, None, None)
            continue
        fetched = fetch_from_item(item)
        if fetched is not None:
            if fetched.content is not None:
                add(fetched.url, fetched.title, fetched.content)
            continue
        for annotation in _annotations(item):
            add(annotation["url"], annotation.get("title"), annotation.get("content"))
    return list(found.values())


def search_count(response: dict[str, Any]) -> int:
    """Searches run in this response: the reported count, or else the search items seen."""
    usage = response.get("usage")
    details = usage.get("server_tool_use_details") if isinstance(usage, dict) else None
    count = details.get("web_search_requests") if isinstance(details, dict) else None
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    return sum(1 for item in _output(response) if search_from_item(item) is not None)
