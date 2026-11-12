"""The one module that knows the shape of the `openrouter:web_search` tool."""

from __future__ import annotations

import json
from typing import Any

from manyminds.core.models import SearchEngine
from manyminds.core.openrouter.websearch import (
    Citation,
    Search,
    citations,
    search_from_item,
    tool_entry,
)
from openrouter_wire import citation, fixture, message_item, search_item


def final_response(name: str) -> dict[str, Any]:
    for line in fixture(name).decode().splitlines():
        if line.startswith("data: {"):
            event = json.loads(line[6:])
            if event["type"] == "response.completed":
                response: dict[str, Any] = event["response"]
                return response
    raise AssertionError("no completed event in fixture")


def test_tool_entry_for_exa() -> None:
    assert tool_entry(SearchEngine.EXA) == {
        "type": "openrouter:web_search",
        "parameters": {"engine": "exa", "max_results": 5, "max_uses": 6},
    }


def test_tool_entry_for_auto() -> None:
    assert tool_entry(SearchEngine.AUTO) == {
        "type": "openrouter:web_search",
        "parameters": {"engine": "auto", "max_results": 5, "max_uses": 6},
    }


def test_citations_from_an_exa_search_have_url_title_and_excerpt() -> None:
    found = citations(final_response("search_exa.sse"))

    assert [(c.url, c.title) for c in found] == [
        (
            "https://www.nasa.gov/wp-content/uploads/static/history/PDFs/"
            "great_wall_less_great_from_space.pdf",
            "Feature",
        ),
        ("https://www.nasa.gov/image-article/great-wall/", "Great Wall"),
        (
            "https://www.scientificamerican.com/article/"
            "no-you-cant-see-the-great-wall-of-china-from-space/",
            "No, You Can\u2019t See the Great Wall of China from Space | Scientific American",
        ),
    ]
    assert found[1].excerpt is not None
    assert "difficult or impossible to see from Earth orbit" in found[1].excerpt


def test_citations_from_a_native_search_are_urls_without_excerpts() -> None:
    found = citations(final_response("search_native.sse"))

    urls = [c.url for c in found]
    assert "https://eol.jsc.nasa.gov/FAQ/default.htm" in urls
    assert "https://en.wikipedia.org/wiki/Great_Wall_of_China" in urls
    assert len(urls) == len(set(urls))
    assert all(c.excerpt is None and c.title is None for c in found)


def test_a_url_seen_as_both_source_and_annotation_is_one_citation_with_the_excerpt() -> None:
    response = {
        "output": [
            search_item("q", ["https://a.example/page", "https://b.example/page"]),
            message_item("notes", [citation("https://a.example/page", "Page A", "some text")]),
        ]
    }

    assert citations(response) == [
        Citation("https://a.example/page", "Page A", "some text"),
        Citation("https://b.example/page", None, None),
    ]


def test_two_excerpts_for_one_url_are_joined() -> None:
    response = {
        "output": [
            message_item(
                "notes",
                [
                    citation("https://a.example/page", "Page A", "first part"),
                    citation("https://a.example/page", "Page A", "second part"),
                ],
            )
        ]
    }

    assert citations(response) == [
        Citation("https://a.example/page", "Page A", "first part\nsecond part")
    ]


def test_search_from_item_reads_both_item_types() -> None:
    ours = search_item("great wall", ["https://a.example/1", "https://a.example/2"])
    native = {"type": "web_search_call", "action": {"type": "search", "query": "wall nasa"}}

    assert search_from_item(ours) == Search(
        "great wall", ("https://a.example/1", "https://a.example/2")
    )
    assert search_from_item(native) == Search("wall nasa", ())


def test_search_from_item_ignores_other_items() -> None:
    assert search_from_item(message_item("text")) is None
    assert search_from_item({"type": "function_call", "name": "shell"}) is None
