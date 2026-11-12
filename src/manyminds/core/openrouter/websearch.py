"""The only module that knows the shape of OpenRouter's `openrouter:web_search` tool.

Built against the beta documentation as of 2026-11-12. Non-native engines (Exa) return each
result as a `url_citation` annotation with an excerpt. Provider-native search returns only a
list of URLs on the search item, and only when the request asks for it with `include`.
"""

from dataclasses import dataclass
from typing import Any

from manyminds.core.models import SearchEngine

MAX_RESULTS_PER_SEARCH = 5
MAX_SEARCHES = 6
_SEARCH_ITEM_TYPES = ("openrouter:web_search", "web_search_call")

REQUEST_FIELDS: dict[str, Any] = {"include": ["web_search_call.action.sources"]}
"""Extra top-level request fields a search call needs."""


@dataclass(frozen=True)
class Citation:
    """One page the search tool returned."""

    url: str
    title: str | None
    excerpt: str | None


@dataclass(frozen=True)
class Search:
    """One search the model ran."""

    query: str
    urls: tuple[str, ...]


def tool_entry(engine: SearchEngine) -> dict[str, Any]:
    return {
        "type": "openrouter:web_search",
        "parameters": {
            "engine": engine.value,
            "max_results": MAX_RESULTS_PER_SEARCH,
            "max_uses": MAX_SEARCHES,
        },
    }


def search_from_item(item: dict[str, Any]) -> Search | None:
    """The search an output item describes, or None if the item is not a search."""
    if item.get("type") not in _SEARCH_ITEM_TYPES:
        return None
    action = item.get("action") or {}
    urls = tuple(
        source["url"]
        for source in action.get("sources") or []
        if isinstance(source, dict) and isinstance(source.get("url"), str)
    )
    return Search(str(action.get("query") or ""), urls)


def citations(response: dict[str, Any]) -> list[Citation]:
    """Every page the search returned in this response, one entry per URL, in order."""
    found: dict[str, Citation] = {}
    for item in response.get("output") or []:
        search = search_from_item(item)
        if search is not None:
            for url in search.urls:
                found.setdefault(url, Citation(url, None, None))
            continue
        for part in item.get("content") or []:
            for annotation in part.get("annotations") or []:
                if annotation.get("type") != "url_citation":
                    continue
                url = annotation.get("url")
                if not isinstance(url, str):
                    continue
                known = found.get(url)
                excerpts = [
                    text
                    for text in (known.excerpt if known else None, annotation.get("content"))
                    if isinstance(text, str) and text
                ]
                found[url] = Citation(
                    url,
                    annotation.get("title") or (known.title if known else None),
                    "\n".join(excerpts) or None,
                )
    return list(found.values())


def search_count(response: dict[str, Any]) -> int:
    details = (response.get("usage") or {}).get("server_tool_use_details") or {}
    count = details.get("web_search_requests")
    return count if isinstance(count, int) else 0
