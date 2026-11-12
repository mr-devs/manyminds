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


async def test_research_returns_a_report_with_sources_the_search_returned(
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
    assert JobEventKind.SEARCHING in kinds
    assert JobEventKind.SOURCES_FOUND in kinds
    assert kinds[-1] is JobEventKind.WRITING
    assert result.report.evidence
    assert any(item.grounded for item in result.report.evidence)
    assert result.usage.searches >= 1
    assert result.usage.cost > 0
