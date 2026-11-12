"""Wire formats asked of the model, kept apart from the domain models.

The JSON schemas are written out by hand because strict structured output needs every
property listed as required and `additionalProperties: false` at every level. The pydantic
models validate whatever comes back, whether or not the provider enforced the schema.
"""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints

from manyminds.core.models import MAX_QUOTE_LENGTH, NonBlank, Stance, WebUrl


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WireEvidence(_Wire):
    url: WebUrl
    title: str | None = None
    quote: Annotated[NonBlank, StringConstraints(max_length=MAX_QUOTE_LENGTH)]
    stance: Stance


class WireReport(_Wire):
    summary: NonBlank
    evidence: list[WireEvidence]
    undetermined: NonBlank


class WireDecomposition(_Wire):
    title: NonBlank
    leads: list[NonBlank]


REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "evidence", "undetermined"],
    "properties": {
        "summary": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["url", "title", "quote", "stance"],
                "properties": {
                    "url": {"type": "string"},
                    "title": {"type": ["string", "null"]},
                    "quote": {"type": "string"},
                    "stance": {"type": "string", "enum": [s.value for s in Stance]},
                },
            },
        },
        "undetermined": {"type": "string"},
    },
}

DECOMPOSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "leads"],
    "properties": {
        "title": {"type": "string"},
        "leads": {"type": "array", "items": {"type": "string"}},
    },
}


def text_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """The `text` request field that asks for strict JSON in the given schema."""
    return {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}}
