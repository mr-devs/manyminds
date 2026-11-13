"""Opt-in smoke tests against the real OpenRouter API. They cost about two cents a run.

    uv run pytest -m live

These check that the request shapes the fixture tests pin are still accepted, and that real
models still answer in a form the adapter can read. Assertions are loose on purpose: model
output varies.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

from manyminds.core.models import JobEventKind, SearchEngine
from manyminds.core.openrouter.adapter import OpenRouterModelClient
from manyminds.core.openrouter.client import build_client
from manyminds.core.ports import Progress

pytestmark = pytest.mark.live

MODEL = "openai/gpt-6-luna"
TEXT = (
    "The Great Wall of China is the only man-made structure visible from space with the naked "
    "eye, and it is more than 21,000 kilometres long."
)


@pytest.fixture
async def client() -> AsyncIterator[OpenRouterModelClient]:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        pytest.fail("OPENROUTER_API_KEY is not set; live tests need a real key.")
    model, http = build_client(key)
    yield model
    await http.aclose()


async def test_decompose_returns_leads(client: OpenRouterModelClient) -> None:
    result = await client.decompose(TEXT, "", count=3, avoid=[], model=MODEL)

    assert result.title
    assert 1 <= len(result.leads) <= 3


async def test_research_hands_back_findings_whose_links_the_search_returned(
    client: OpenRouterModelClient,
) -> None:
    progress: list[Progress] = []

    result = await client.research(
        "The Great Wall of China is visible from space with the naked eye.",
        TEXT,
        "",
        model=MODEL,
        search=SearchEngine.EXA,
        on_progress=progress.append,
    )

    kinds = [p.kind for p in progress]
    print(result.report.notes)
    print("not returned:", result.report.unreturned_links)
    assert JobEventKind.SEARCHING in kinds
    assert JobEventKind.SOURCES_FOUND in kinds
    assert "http" in result.report.notes
    assert len(result.report.unreturned_links) <= 1
    assert result.usage.searches >= 1
    assert result.usage.cost > 0


FINDINGS = (
    "## Findings\n\nNASA says the wall is not visible to the naked eye from low Earth orbit.\n\n"
    "1. **Great Wall:** https://www.nasa.gov/great-wall\n"
    '   **Passage:** "The Great Wall is difficult or impossible to see from Earth orbit."\n'
    "   Undermines the lead.\n\n"
    "Could not find: whether any astronaut has photographed it unaided."
)


def _context() -> object:
    from manyminds.core.models import MessageRole, Report
    from manyminds.core.ports import ChatContext, LeadNote, PastTurn

    return ChatContext(
        turns=(PastTurn(MessageRole.USER, TEXT),),
        leads=(
            LeadNote(
                "The Great Wall is visible from space with the naked eye.",
                "finished",
                (Report(notes=FINDINGS),),
            ),
            LeadNote("The Great Wall is more than 21,000 kilometres long.", "failed"),
        ),
    )


async def test_the_conversation_answers_from_findings_and_can_propose_leads(
    client: OpenRouterModelClient,
) -> None:
    reply = await client.converse(
        "Summarise what has been found so far, and suggest one more lead about who first "
        "made the claim.",
        _context(),  # type: ignore[arg-type]
        model=MODEL,
    )

    print(reply)
    assert reply.body.strip()
    assert "nasa" in reply.body.lower()
    assert 1 <= len(reply.leads) <= 5


async def test_the_report_is_written_from_what_was_handed_back(
    client: OpenRouterModelClient,
) -> None:
    reply = await client.write_report(_context(), model=MODEL)  # type: ignore[arg-type]

    print(reply.body)
    assert "nasa.gov/great-wall" in reply.body
    assert "fail" in reply.body.lower()
