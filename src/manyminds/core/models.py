"""Domain models."""

from datetime import datetime
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


MAX_QUOTE_LENGTH = 2000


class Stance(StrEnum):
    """How one quoted passage bears on the lead. Not a judgement on the claim."""

    SUPPORTS = "supports"
    UNDERMINES = "undermines"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceItem(_Strict):
    url: WebUrl
    title: str | None = None
    quote: Annotated[NonBlank, StringConstraints(max_length=MAX_QUOTE_LENGTH)]
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


class SearchEngine(StrEnum):
    AUTO = "auto"
    EXA = "exa"


class LeadOrigin(StrEnum):
    GENERATED = "generated"
    MANUAL = "manual"
    CONVERSATION = "conversation"


class LeadState(StrEnum):
    DRAFT = "draft"
    LAUNCHED = "launched"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ErrorKind(StrEnum):
    AUTH = "auth"
    CREDITS = "credits"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    PROVIDER = "provider"
    REFUSAL = "refusal"
    INVALID_OUTPUT = "invalid_output"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class JobEventKind(StrEnum):
    STARTED = "started"
    THINKING = "thinking"
    SEARCHING = "searching"
    READING = "reading"
    SOURCES_FOUND = "sources_found"
    MESSAGE = "message"
    NOTE = "note"
    """A step described in the app's own words."""
    WRITING = "writing"
    RETRYING = "retrying"
    FINISHED = "finished"
    FAILED = "failed"


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True)


class Usage(_Record):
    """What one job consumed, summed over every model call it made."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    """US dollars, as reported by the provider."""
    searches: int = 0


class Check(_Record):
    """One pasted text and everything that follows from it."""

    id: str
    title: str
    source_text: str
    instructions: str
    created_at: datetime
    updated_at: datetime


class Lead(_Record):
    """A specific thread of research, editable until it is launched."""

    id: str
    check_id: str
    text: str
    position: int
    origin: LeadOrigin
    state: LeadState
    created_at: datetime
    message_id: str | None = None
    """The reply in the conversation that this lead is listed under."""


class Message(_Record):
    """One turn in a check's conversation. A reply may have leads listed under it."""

    id: str
    check_id: str
    seq: int
    role: MessageRole
    status: MessageStatus
    body: str
    error_message: str | None
    created_at: datetime


class Thread(_Record):
    """A launched lead. Its status is derived from its jobs."""

    id: str
    check_id: str
    lead_id: str
    lead_text: str
    created_at: datetime


class Job(_Record):
    """One model researching one thread."""

    id: str
    thread_id: str
    model: str
    status: JobStatus
    search_engine: SearchEngine
    instructions: str
    attempt: int
    error_kind: ErrorKind | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    usage: Usage | None = None
    """Set when the job finishes. Failed jobs do not record what they used."""


class JobEvent(_Record):
    """One entry in a job's transcript: a step, the model's thinking, or what it wrote."""

    job_id: str
    seq: int
    kind: JobEventKind
    detail: str
    created_at: datetime


class MessageStep(_Record):
    """One step taken while a reply was being worked out, such as a page being opened."""

    message_id: str
    seq: int
    kind: JobEventKind
    detail: str
    created_at: datetime


class ThreadStatus(StrEnum):
    """What a thread's row shows, derived from its jobs."""

    QUEUED = "queued"
    WORKING = "working"
    FINISHED = "finished"
    FAILED = "failed"
