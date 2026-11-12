"""The only module that knows the shape of OpenRouter's `openrouter:web_search` tool.

Built against the beta documentation as of 2026-11-12. Non-native engines (Exa) return each
result as a `url_citation` annotation with an excerpt. Provider-native search returns only a
list of URLs on the search item, and only when the request asks for it with `include`.
"""

from dataclasses import dataclass
from typing import Any

from manyminds.core.models import SearchEngine
from manyminds.core.safety import PASSAGE_BREAK

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
    """Every page the search returned in this response, one entry per URL, in order."""
    found: dict[str, Citation] = {}
    for item in _output(response):
        search = search_from_item(item)
        if search is not None:
            for url in search.urls:
                found.setdefault(url, Citation(url, None, None))
            continue
        for annotation in _annotations(item):
            url = annotation["url"]
            known = found.get(url)
            title = annotation.get("title")
            found[url] = Citation(
                url,
                (title if isinstance(title, str) and title else None)
                or (known.title if known else None),
                join_excerpts(known.excerpt if known else None, annotation.get("content")),
            )
    return list(found.values())


def join_excerpts(*excerpts: object) -> str | None:
    """Several excerpts of one page as one text, kept apart so no quote can span two."""
    kept = [text for text in excerpts if isinstance(text, str) and text]
    return f"\n{PASSAGE_BREAK}\n".join(kept) or None


def search_count(response: dict[str, Any]) -> int:
    """Searches run in this response: the reported count, or else the search items seen."""
    usage = response.get("usage")
    details = usage.get("server_tool_use_details") if isinstance(usage, dict) else None
    count = details.get("web_search_requests") if isinstance(details, dict) else None
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    return sum(1 for item in _output(response) if search_from_item(item) is not None)
