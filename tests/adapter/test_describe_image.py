"""Showing the model an image the user attached."""

from __future__ import annotations

import pytest

from manyminds.core import prompts
from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind
from manyminds.core.openrouter.adapter import OpenRouterModelClient
from manyminds.core.openrouter.transport import Transport
from openrouter_wire import API_KEY, Wire, error_response, text_reply


async def describe(wire: Wire, data: bytes = b"\x89PNG-bytes") -> str:
    async with wire.http() as http:
        client = OpenRouterModelClient(Transport(API_KEY, http))
        return await client.describe_image("image/png", data, model="vendor/model-b")


async def test_the_image_itself_is_sent_and_its_description_returned() -> None:
    wire = Wire(text_reply("  A chat screenshot.  "))

    said = await describe(wire)

    assert said == "A chat screenshot."
    (body,) = wire.bodies
    assert body["model"] == "vendor/model-b"
    assert body["instructions"] == prompts.IMAGE_INSTRUCTIONS
    assert "tools" not in body
    # base64 of b"\x89PNG-bytes"
    assert {
        "type": "input_image",
        "image_url": "data:image/png;base64,iVBORy1ieXRlcw==",
    } in body["input"][0]["content"]


async def test_a_model_that_says_nothing_about_the_image_is_an_error() -> None:
    with pytest.raises(ModelError) as caught:
        await describe(Wire(text_reply("   ")))

    assert caught.value.kind is ErrorKind.INVALID_OUTPUT


async def test_a_refused_image_is_reported() -> None:
    with pytest.raises(ModelError) as caught:
        await describe(Wire(error_response(400)))

    assert caught.value.kind is ErrorKind.UNKNOWN
