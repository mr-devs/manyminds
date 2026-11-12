"""Interfaces the core depends on. Implementations live elsewhere."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from manyminds.core.models import JobEventKind, Report, SearchEngine


@dataclass(frozen=True)
class Decomposition:
    """A short title for the pasted text and the leads worth researching."""

    title: str
    leads: list[str]


@dataclass(frozen=True)
class Progress:
    """One step of live progress reported while a model call is running."""

    kind: JobEventKind
    detail: str = ""


ProgressCallback = Callable[[Progress], None]


@dataclass(frozen=True)
class ResearchResult:
    report: Report


class ModelClient(Protocol):
    """Everything the app asks of a language model. Failures raise ModelError."""

    async def decompose(
        self, text: str, instructions: str, *, count: int, avoid: Sequence[str], model: str
    ) -> Decomposition: ...

    async def research(
        self,
        lead: str,
        source_text: str,
        instructions: str,
        *,
        model: str,
        search: SearchEngine,
        on_progress: ProgressCallback,
    ) -> ResearchResult: ...
