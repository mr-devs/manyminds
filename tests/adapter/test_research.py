"""Research through OpenRouter: one call that searches, reads, and hands back its findings."""

from __future__ import annotations

import pytest

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind, JobEventKind, SearchEngine
from manyminds.core.openrouter.adapter import OpenRouterModelClient
from manyminds.core.openrouter.transport import Transport
from manyminds.core.ports import Progress, ResearchResult
from openrouter_wire import (
    API_KEY,
    Wire,
    fetch_item,
    fixture,
    message_item,
    reasoning_item,
    search_item,
    stream_of,
)

LEAD = "The Great Wall of China is visible from space with the naked eye."
NASA_IMAGE = "https://www.nasa.gov/image-article/great-wall/"
SCIAM = (
    "https://www.scientificamerican.com/article/no-you-cant-see-the-great-wall-of-china-from-space/"
)
NASA_PDF = "https://www.nasa.gov/wp-content/uploads/static/history/PDFs/great_wall_less_great_from_space.pdf"


async def research(
    wire: Wire,
    *,
    search: SearchEngine = SearchEngine.EXA,
    instructions: str = "",
    source_text: str = "A post claiming the wall can be seen from space.",
    progress: list[Progress] | None = None,
) -> ResearchResult:
    seen = progress if progress is not None else []
    async with wire.http() as http:
        client = OpenRouterModelClient(Transport(API_KEY, http))
        return await client.research(
            LEAD,
            source_text,
            instructions,
            model="vendor/model-a",
            search=search,
            on_progress=seen.append,
        )


async def failure(wire: Wire) -> ModelError:
    with pytest.raises(ModelError) as caught:
        await research(wire)
    return caught.value


async def test_the_search_call_has_the_search_and_fetch_tools_and_no_schema() -> None:
    wire = Wire(fixture("search_exa.sse"))

    await research(wire, instructions="Prefer primary sources.")

    first = wire.bodies[0]
    assert first["model"] == "vendor/model-a"
    assert first["stream"] is True
    assert first["tools"] == [
        {
            "type": "openrouter:web_search",
            "parameters": {"engine": "exa", "max_results": 5, "max_uses": 6},
        },
        {
            "type": "openrouter:web_fetch",
            "parameters": {"engine": "exa", "max_uses": 6, "max_content_tokens": 8000},
        },
    ]
    assert "text" not in first
    assert "response_format" not in first
    assert LEAD in first["input"]
    assert "A post claiming the wall can be seen from space." in first["input"]
    assert "Prefer primary sources." in first["input"]


async def test_the_engine_setting_reaches_the_tool() -> None:
    wire = Wire(fixture("search_native.sse"))

    await research(wire, search=SearchEngine.AUTO)

    assert wire.bodies[0]["tools"][0]["parameters"]["engine"] == "auto"


async def test_research_is_a_single_call() -> None:
    wire = Wire(fixture("search_exa.sse"))

    await research(wire)

    assert len(wire.bodies) == 1
    assert "text" not in wire.bodies[0]  # no fixed format: the agent writes its findings freely


async def test_what_the_agent_wrote_last_is_handed_back_as_its_findings() -> None:
    result = await research(Wire(fixture("search_exa.sse")))

    assert result.report.notes.startswith("## Evidence\n\n1. **NASA")
    assert "## What could not be determined" in result.report.notes
    assert result.report.unreturned_links == []


async def test_what_it_wrote_along_the_way_is_progress_and_not_part_of_the_findings() -> None:
    search = stream_of(
        message_item("I will start with NASA."),
        search_item("nasa great wall", ["https://a.example/page"]),
        message_item("## Findings\n\nOne source: https://a.example/page"),
        message_item("Nothing else was found."),
    )
    progress: list[Progress] = []

    result = await research(Wire(search), progress=progress)

    assert result.report.notes == (
        "## Findings\n\nOne source: https://a.example/page\n\nNothing else was found."
    )
    assert [(p.kind, p.detail) for p in progress] == [
        (JobEventKind.MESSAGE, "I will start with NASA."),
        (JobEventKind.SEARCHING, "nasa great wall"),
        (JobEventKind.SOURCES_FOUND, "https://a.example/page"),
    ]


async def test_thinking_after_the_last_words_does_not_discard_them() -> None:
    search = stream_of(
        search_item("q", ["https://a.example/page"]),
        message_item("The findings."),
        reasoning_item("Done."),
    )

    result = await research(Wire(search))

    assert result.report.notes == "The findings."


# -- links the search never returned ---------------------------------------------------------


def findings(text: str, *returned: str, opened: str | None = None) -> bytes:
    items = [search_item("q", list(returned))]
    if opened:
        items.append(fetch_item(opened, "A page", "Its text."))
    return stream_of(*items, message_item(text))


async def test_links_the_search_returned_or_the_agent_opened_are_not_flagged() -> None:
    text = (
        "See https://a.example/page and [the report](https://www.b.example/report/) "
        "and https://c.example/opened."
    )
    body = findings(
        text,
        "https://a.example/page",
        "https://b.example/report",
        opened="https://c.example/opened",
    )

    result = await research(Wire(body))

    assert result.report.unreturned_links == []


async def test_a_link_the_search_never_returned_is_flagged() -> None:
    text = "See https://a.example/page and https://made-up.example/proof and again https://made-up.example/proof"

    result = await research(Wire(findings(text, "https://a.example/page")))

    assert result.report.unreturned_links == ["https://made-up.example/proof"]


async def test_a_lookalike_host_or_another_page_on_the_same_site_is_flagged() -> None:
    text = "https://nasa.gov.evil.example/great-wall and https://www.nasa.gov/other-page"

    result = await research(Wire(findings(text, "https://www.nasa.gov/great-wall")))

    assert result.report.unreturned_links == [
        "https://nasa.gov.evil.example/great-wall",
        "https://www.nasa.gov/other-page",
    ]


async def test_native_search_results_count_as_returned() -> None:
    result = await research(Wire(fixture("search_native.sse")), search=SearchEngine.AUTO)

    assert result.report.notes.startswith("## Evidence found")
    assert result.report.unreturned_links == []


# -- progress and usage ----------------------------------------------------------------------


async def test_progress_reports_searches_and_sources() -> None:
    progress: list[Progress] = []

    await research(Wire(fixture("search_exa.sse")), progress=progress)

    assert [p.kind for p in progress] == [
        JobEventKind.SEARCHING,
        JobEventKind.SOURCES_FOUND,
        JobEventKind.SEARCHING,
    ]
    assert progress[0].detail == (
        "Great Wall of China visible from space naked eye astronaut NASA visibility "
        "low Earth orbit evidence"
    )
    assert progress[1].detail == f"{NASA_PDF}\n{NASA_IMAGE}\n{SCIAM}"


async def test_reasoning_summaries_are_reported_as_thinking() -> None:
    search = stream_of(
        reasoning_item("I should look for what NASA says.", "Then check astronaut accounts."),
        reasoning_item(),
        search_item("nasa great wall", ["https://a.example/page"]),
        message_item("Found one source."),
    )
    progress: list[Progress] = []

    await research(Wire(search), progress=progress)

    assert progress[0] == Progress(
        JobEventKind.THINKING,
        "I should look for what NASA says.\n\nThen check astronaut accounts.",
    )
    assert [p.kind for p in progress] == [
        JobEventKind.THINKING,
        JobEventKind.SEARCHING,
        JobEventKind.SOURCES_FOUND,
    ]


async def test_usage_is_what_the_one_call_used() -> None:
    result = await research(Wire(fixture("search_exa.sse")))

    assert (result.usage.input_tokens, result.usage.output_tokens) == (6672, 1046)
    assert result.usage.searches == 2
    assert result.usage.cost == pytest.approx(0.00801378)


# -- failures --------------------------------------------------------------------------------


async def test_a_refusal_part_fails_with_the_models_own_words() -> None:
    refusal = {
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "refusal", "refusal": "I can't help with that topic."}],
    }

    error = await failure(Wire(stream_of(refusal)))

    assert error.kind is ErrorKind.REFUSAL
    assert "I can't help with that topic." in error.message


async def test_a_content_filter_stop_is_a_refusal() -> None:
    body = stream_of(
        message_item("I started to answer but"),
        status="incomplete",
        incomplete_reason="content_filter",
    )

    error = await failure(Wire(body))

    assert error.kind is ErrorKind.REFUSAL
    assert "I started to answer but" in error.message


async def test_running_out_of_output_tokens_is_a_provider_error() -> None:
    body = stream_of(
        message_item("partial"), status="incomplete", incomplete_reason="max_output_tokens"
    )

    error = await failure(Wire(body))

    assert error.kind is ErrorKind.PROVIDER


async def test_a_search_call_with_no_text_fails_as_invalid_output() -> None:
    error = await failure(Wire(stream_of(search_item("q", ["https://a.example/page"]))))

    assert error.kind is ErrorKind.INVALID_OUTPUT


async def test_a_stream_that_ends_before_finishing_is_a_provider_error() -> None:
    from openrouter_wire import sse

    body = sse({"type": "response.created", "response": {"status": "in_progress"}})

    error = await failure(Wire(body))

    assert error.kind is ErrorKind.PROVIDER


async def test_a_transport_failure_keeps_its_kind() -> None:
    from openrouter_wire import error_response

    error = await failure(Wire(error_response(429)))

    assert error.kind is ErrorKind.RATE_LIMIT
