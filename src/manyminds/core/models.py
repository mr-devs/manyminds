"""Domain models."""

from enum import StrEnum
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _require_web_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise ValueError("must be an http or https URL with a host")
    return value


WebUrl = Annotated[NonBlank, AfterValidator(_require_web_url)]


class Stance(StrEnum):
    """How one quoted passage bears on the lead. Not a judgement on the claim."""

    SUPPORTS = "supports"
    UNDERMINES = "undermines"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceItem(_Strict):
    url: WebUrl
    title: str | None = None
    quote: NonBlank
    stance: Stance
    grounded: bool = False
    """The URL was among the results the search tool returned for this job."""
    quote_matched: bool | None = None
    """The quote was found in the returned excerpt; None when there was no excerpt."""


class Report(_Strict):
    """Structured evidence for the user to judge. Deliberately has no verdict."""

    summary: NonBlank
    evidence: list[EvidenceItem]
    undetermined: NonBlank
