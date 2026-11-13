"""Wire formats asked of the model, kept apart from the domain models.

The JSON schemas are written out by hand because strict structured output needs every
property listed as required and `additionalProperties: false` at every level. The pydantic
models validate whatever comes back, whether or not the provider enforced the schema.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

from manyminds.core.models import NonBlank


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WireDecomposition(_Wire):
    title: NonBlank
    leads: list[NonBlank]


class WireChatReply(_Wire):
    reply: str
    leads: list[str]


DECOMPOSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "leads"],
    "properties": {
        "title": {"type": "string"},
        "leads": {"type": "array", "items": {"type": "string"}},
    },
}


CHAT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reply", "leads"],
    "properties": {
        "reply": {"type": "string"},
        "leads": {"type": "array", "items": {"type": "string"}},
    },
}


def text_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """The `text` request field that asks for strict JSON in the given schema."""
    return {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}}
