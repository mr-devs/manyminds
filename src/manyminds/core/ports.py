"""Interfaces the core depends on. Implementations live elsewhere."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from manyminds.core.models import JobEventKind, MessageRole, Report, SearchEngine, Usage


@dataclass(frozen=True)
class Decomposition:
    """A short title for the pasted text and the leads worth researching."""

    title: str
    leads: list[str]
    seen: str = ""
    """What was read from links and images in the text, in plain words, for the user to see."""


@dataclass(frozen=True)
class Progress:
    """One step of live progress reported while a model call is running."""

    kind: JobEventKind
    detail: str = ""


ProgressCallback = Callable[[Progress], None]


@dataclass(frozen=True)
class ResearchResult:
    report: Report
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True)
class PastTurn:
    """Something already said in the conversation."""

    role: MessageRole
    body: str


NOT_STARTED = "not started"
IN_PROGRESS = "in progress"
FINISHED = "finished"
FAILED = "failed"


@dataclass(frozen=True)
class LeadNote:
    """A lead on the check, how far its research has got, and any finished reports."""

    text: str
    state: str
    reports: tuple[Report, ...] = ()


@dataclass(frozen=True)
class ChatContext:
    """What the chat model is shown besides the new message."""

    turns: tuple[PastTurn, ...]
    leads: tuple[LeadNote, ...]


@dataclass(frozen=True)
class ChatReply:
    body: str
    leads: list[str] = field(default_factory=list)
    """Leads proposed for research. They wait for the user; nothing starts by itself."""


class ModelClient(Protocol):
    """Everything the app asks of a language model. Failures raise ModelError."""

    async def decompose(
        self,
        text: str,
        instructions: str,
        *,
        count: int,
        avoid: Sequence[str],
        model: str,
        on_progress: ProgressCallback | None = None,
    ) -> Decomposition: ...

    async def converse(
        self,
        message: str,
        context: ChatContext,
        *,
        model: str,
        search: SearchEngine = SearchEngine.EXA,
        on_progress: ProgressCallback | None = None,
    ) -> ChatReply: ...

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
