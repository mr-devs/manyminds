"""Turning pasted text into a title and a list of leads."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind
from manyminds.core.openrouter.adapter import OpenRouterModelClient
from manyminds.core.openrouter.transport import Transport
from manyminds.core.ports import Decomposition
from openrouter_wire import API_KEY, Wire, fixture, json_reply, text_reply

TEXT = "The Great Wall is visible from space, and it is 21,000 km long."
REPLY = {
    "title": "Great Wall claims",
    "leads": [
        "The Great Wall of China is visible from space with the naked eye.",
        "The Great Wall of China is about 21,000 km long.",
    ],
}


async def decompose(
    wire: Wire, *, count: int = 5, avoid: Sequence[str] = (), instructions: str = ""
) -> Decomposition:
    async with wire.http() as http:
        client = OpenRouterModelClient(Transport(API_KEY, http))
        return await client.decompose(
            TEXT, instructions, count=count, avoid=avoid, model="vendor/model-b"
        )


async def test_a_valid_reply_becomes_a_decomposition() -> None:
    result = await decompose(Wire(json_reply(REPLY)))

    assert result == Decomposition(
        title="Great Wall claims",
        leads=[
            "The Great Wall of China is visible from space with the naked eye.",
            "The Great Wall of China is about 21,000 km long.",
        ],
    )


async def test_the_request_has_a_schema_and_no_tools() -> None:
    wire = Wire(json_reply(REPLY))

    await decompose(wire, count=3, avoid=["An old lead."], instructions="Focus on numbers.")

    body = wire.bodies[0]
    assert len(wire.bodies) == 1
    assert body["model"] == "vendor/model-b"
    assert "tools" not in body
    assert body["provider"] == {"require_parameters": True}
    schema = body["text"]["format"]["schema"]
    assert body["text"]["format"]["strict"] is True
    assert schema["required"] == ["title", "leads"]
    assert schema["additionalProperties"] is False
    assert TEXT in body["input"]
    assert "Focus on numbers." in body["input"]
    assert "An old lead." in body["input"]
    assert "3" in body["instructions"] or "3" in body["input"]


async def test_leads_beyond_the_requested_count_are_dropped() -> None:
    reply = {"title": "t", "leads": ["one", "two", "three", "four"]}

    result = await decompose(Wire(json_reply(reply)), count=2)

    assert result.leads == ["one", "two"]


async def test_leads_are_trimmed() -> None:
    reply = {"title": "  A title  ", "leads": ["  padded lead  "]}

    result = await decompose(Wire(json_reply(reply)))

    assert result == Decomposition(title="A title", leads=["padded lead"])


BAD_REPLIES: list[Any] = [
    "Sure! Here are some leads.",
    {"title": "t"},
    {"title": "t", "leads": "one lead as a string"},
    {"title": "t", "leads": ["fine", "   "]},
    {"title": "", "leads": ["fine"]},
    {"title": "t", "leads": ["fine"], "start_research": True},
]


def reply_for(bad: Any) -> bytes:
    return text_reply(bad) if isinstance(bad, str) else json_reply(bad)


@pytest.mark.parametrize("bad", BAD_REPLIES)
async def test_an_invalid_reply_gets_one_repair_attempt(bad: Any) -> None:
    wire = Wire(reply_for(bad), json_reply(REPLY))

    result = await decompose(wire)

    assert result.title == "Great Wall claims"
    assert len(wire.bodies) == 2
    assert "tools" not in wire.bodies[1]


@pytest.mark.parametrize("bad", BAD_REPLIES)
async def test_a_second_invalid_reply_fails(bad: Any) -> None:
    wire = Wire(reply_for(bad), reply_for(bad))

    with pytest.raises(ModelError) as caught:
        await decompose(wire)

    assert caught.value.kind is ErrorKind.INVALID_OUTPUT
    assert len(wire.bodies) == 2


async def test_a_real_captured_schema_stream_is_read_to_its_final_text() -> None:
    """The captured reply is a report, not a decomposition, so it must be rejected twice."""
    wire = Wire(fixture("schema_only.sse"), fixture("schema_only.sse"))

    with pytest.raises(ModelError) as caught:
        await decompose(wire)

    assert caught.value.kind is ErrorKind.INVALID_OUTPUT
    assert "I could not run web searches in this session" in wire.bodies[1]["input"]
