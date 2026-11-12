"""Research through OpenRouter: a search call, then a no-tools call that writes the report."""

from __future__ import annotations

from typing import Any

import pytest

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind, JobEventKind, SearchEngine, Stance
from manyminds.core.openrouter.adapter import OpenRouterModelClient
from manyminds.core.openrouter.transport import Transport
from manyminds.core.ports import Progress, ResearchResult
from openrouter_wire import (
    API_KEY,
    Wire,
    citation,
    fixture,
    json_reply,
    message_item,
    reasoning_item,
    search_item,
    stream_of,
    text_reply,
)

LEAD = "The Great Wall of China is visible from space with the naked eye."
NASA_IMAGE = "https://www.nasa.gov/image-article/great-wall/"
SCIAM = (
    "https://www.scientificamerican.com/article/no-you-cant-see-the-great-wall-of-china-from-space/"
)
NASA_PDF = "https://www.nasa.gov/wp-content/uploads/static/history/PDFs/great_wall_less_great_from_space.pdf"

REPORT = {
    "summary": "NASA pages say the wall is hard or impossible to see unaided from orbit.",
    "evidence": [
        {
            "url": NASA_IMAGE,
            "title": "Great Wall",
            "quote": "difficult or impossible to see from Earth orbit",
            "stance": "undermines",
        },
        {
            "url": SCIAM,
            "title": "No, You Can\u2019t See the Great Wall of China from Space",
            "quote": "astronauts wave at the wall every morning",
            "stance": "supports",
        },
        {
            "url": "https://example.org/never-returned",
            "title": "Made up",
            "quote": "it is plainly visible",
            "stance": "supports",
        },
    ],
    "undetermined": "Whether it can be seen under rare lighting conditions.",
}


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
    wire = Wire(fixture("search_exa.sse"), json_reply(REPORT))

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
    wire = Wire(fixture("search_native.sse"), json_reply(REPORT))

    await research(wire, search=SearchEngine.AUTO)

    assert wire.bodies[0]["tools"][0]["parameters"]["engine"] == "auto"


async def test_the_report_call_has_no_tools_and_a_strict_schema() -> None:
    wire = Wire(fixture("search_exa.sse"), json_reply(REPORT))

    await research(wire)

    assert len(wire.bodies) == 2
    second = wire.bodies[1]
    assert "tools" not in second
    assert second["model"] == "vendor/model-a"
    assert second["provider"] == {"require_parameters": True}
    schema_format = second["text"]["format"]
    assert schema_format["type"] == "json_schema"
    assert schema_format["strict"] is True
    assert schema_format["schema"]["required"] == ["summary", "evidence", "undetermined"]
    assert schema_format["schema"]["additionalProperties"] is False
    item = schema_format["schema"]["properties"]["evidence"]["items"]
    assert item["required"] == ["url", "title", "quote", "stance"]
    assert item["properties"]["stance"]["enum"] == ["supports", "undermines"]
    assert item["additionalProperties"] is False


async def test_the_report_call_is_given_the_search_results_and_the_notes() -> None:
    wire = Wire(fixture("search_exa.sse"), json_reply(REPORT))

    await research(wire)

    given = wire.bodies[1]["input"]
    assert LEAD in given
    assert NASA_IMAGE in given
    assert "is difficult or impossible to see from Earth orbit" in given
    assert "## Evidence" in given


async def test_a_valid_report_is_returned_with_grounding_flags() -> None:
    result = await research(Wire(fixture("search_exa.sse"), json_reply(REPORT)))

    report = result.report
    assert (
        report.summary == "NASA pages say the wall is hard or impossible to see unaided from orbit."
    )
    assert report.undetermined == "Whether it can be seen under rare lighting conditions."
    assert [e.url for e in report.evidence] == [
        NASA_IMAGE,
        SCIAM,
        "https://example.org/never-returned",
    ]
    assert [e.stance for e in report.evidence] == [
        Stance.UNDERMINES,
        Stance.SUPPORTS,
        Stance.SUPPORTS,
    ]
    assert [e.grounded for e in report.evidence] == [True, True, False]
    assert [e.quote_matched for e in report.evidence] == [True, False, None]


async def test_a_quote_matches_despite_different_spacing_and_curly_quotes() -> None:
    search = stream_of(
        search_item("q", ["https://a.example/page"]),
        message_item(
            "notes",
            [
                citation(
                    "https://a.example/page", "A", "The wall isn\u2019t\n visible   from the moon."
                )
            ],
        ),
    )
    report = {
        "summary": "s",
        "evidence": [
            {
                "url": "https://a.example/page",
                "title": "A",
                "quote": "the wall isn't visible from the moon",
                "stance": "undermines",
            }
        ],
        "undetermined": "u",
    }

    result = await research(Wire(search, json_reply(report)))

    assert result.report.evidence[0].quote_matched is True


async def test_native_search_grounds_urls_but_cannot_check_quotes() -> None:
    report = {
        "summary": "s",
        "evidence": [
            {
                "url": "https://eol.jsc.nasa.gov/FAQ/default.htm?utm_source=openai",
                "title": "FAQ",
                "quote": "The Great Wall is not visible to the naked eye from orbit",
                "stance": "undermines",
            }
        ],
        "undetermined": "u",
    }
    wire = Wire(fixture("search_native.sse"), json_reply(report))

    result = await research(wire, search=SearchEngine.AUTO)

    assert result.report.evidence[0].grounded is True
    assert result.report.evidence[0].quote_matched is None


async def test_progress_reports_searches_sources_notes_and_writing() -> None:
    progress: list[Progress] = []

    await research(Wire(fixture("search_exa.sse"), json_reply(REPORT)), progress=progress)

    assert [p.kind for p in progress] == [
        JobEventKind.SEARCHING,
        JobEventKind.SOURCES_FOUND,
        JobEventKind.SEARCHING,
        JobEventKind.MESSAGE,
        JobEventKind.WRITING,
    ]
    assert progress[0].detail == (
        "Great Wall of China visible from space naked eye astronaut NASA visibility "
        "low Earth orbit evidence"
    )
    assert progress[1].detail == f"{NASA_PDF}\n{NASA_IMAGE}\n{SCIAM}"
    assert progress[2].detail == (
        "Great Wall of China naked eye from low Earth orbit astronauts visible unaided eye "
        "NASA quote conditions shadow"
    )
    assert progress[3].detail.startswith("## Evidence\n\n1. **NASA")
    assert progress[4].detail == ""


async def test_reasoning_summaries_are_reported_as_thinking() -> None:
    search = stream_of(
        reasoning_item("I should look for what NASA says.", "Then check astronaut accounts."),
        reasoning_item(),
        search_item("nasa great wall", ["https://a.example/page"]),
        message_item("Found one source."),
    )
    progress: list[Progress] = []

    await research(Wire(search, json_reply(REPORT)), progress=progress)

    assert progress[0] == Progress(
        JobEventKind.THINKING,
        "I should look for what NASA says.\n\nThen check astronaut accounts.",
    )
    assert [p.kind for p in progress] == [
        JobEventKind.THINKING,
        JobEventKind.SEARCHING,
        JobEventKind.SOURCES_FOUND,
        JobEventKind.MESSAGE,
        JobEventKind.WRITING,
    ]


async def test_usage_is_summed_over_both_calls() -> None:
    report_usage = {"input_tokens": 100, "output_tokens": 50, "cost": 0.001}
    wire = Wire(fixture("search_exa.sse"), json_reply(REPORT, usage=report_usage))

    result = await research(wire)

    assert (result.usage.input_tokens, result.usage.output_tokens) == (6772, 1096)
    assert result.usage.searches == 2
    assert result.usage.cost == pytest.approx(0.00901378)


BAD_REPORTS: list[Any] = [
    "Here is your report: the wall is not visible.",
    '{"summary": "cut off',
    {"summary": "s", "evidence": []},
    {**REPORT, "evidence": [{**REPORT["evidence"][0], "stance": "refutes"}]},  # type: ignore[dict-item]
    {**REPORT, "evidence": [{"url": NASA_IMAGE, "stance": "supports"}]},
    {**REPORT, "evidence": [{**REPORT["evidence"][0], "quote": "   "}]},  # type: ignore[dict-item]
    {**REPORT, "summary": ""},
    ["not", "an", "object"],
]


def reply_for(bad: Any) -> bytes:
    return text_reply(bad) if isinstance(bad, str) else json_reply(bad)


@pytest.mark.parametrize("bad", BAD_REPORTS)
async def test_an_invalid_report_gets_one_repair_attempt(bad: Any) -> None:
    wire = Wire(fixture("search_exa.sse"), reply_for(bad), json_reply(REPORT))

    result = await research(wire)

    assert len(wire.bodies) == 3
    assert result.report.evidence[0].url == NASA_IMAGE
    repair = wire.bodies[2]
    assert "tools" not in repair
    assert repair["text"]["format"]["strict"] is True
    assert repair["provider"] == {"require_parameters": True}


async def test_the_repair_request_includes_the_rejected_output() -> None:
    bad = {"summary": "s", "evidence": [], "undetermined": "u", "verdict": "false"}
    wire = Wire(fixture("search_exa.sse"), json_reply(bad), json_reply(REPORT))

    await research(wire)

    assert '"verdict": "false"' in wire.bodies[2]["input"]
    assert "verdict" in wire.bodies[2]["input"].split('"verdict": "false"')[1]


@pytest.mark.parametrize("bad", BAD_REPORTS)
async def test_a_second_invalid_report_fails_the_job(bad: Any) -> None:
    wire = Wire(fixture("search_exa.sse"), reply_for(bad), reply_for(bad))

    error = await failure(wire)

    assert error.kind is ErrorKind.INVALID_OUTPUT
    assert len(wire.bodies) == 3


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


async def test_a_transport_failure_in_the_report_call_keeps_its_kind() -> None:
    from openrouter_wire import error_response

    error = await failure(Wire(fixture("search_exa.sse"), error_response(429)))

    assert error.kind is ErrorKind.RATE_LIMIT
