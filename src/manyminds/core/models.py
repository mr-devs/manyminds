"""Domain models."""

from collections.abc import Sequence
from dataclasses import dataclass
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


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Report(_Strict):
    """What a research agent hands back to the main conversation: its findings, as it wrote
    them. There is no verdict field; the agent is told to give none."""

    notes: NonBlank
    """Markdown. Shown formatted, never as markup."""
    unreturned_links: list[str] = []
    """Web addresses written in the notes that neither the search nor a page the agent
    opened returned. They are flagged for the user, since the agent may have made them up."""


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


class MessageKind(StrEnum):
    REPLY = "reply"
    HANDBACK = "handback"
    """A research thread reporting back. Its content is the thread's job, not a body."""
    REPORT = "report"
    """The report written once every started lead has finished."""


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
    kind: MessageKind = MessageKind.REPLY
    job_id: str | None = None
    """For a hand-back, the research job that finished."""


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


@dataclass(frozen=True)
class ImageFile:
    """An image the user attached, as it arrived."""

    media_type: str
    data: bytes


class Attachment(_Record):
    """An image kept with the message it was attached to."""

    id: str
    message_id: str
    position: int
    media_type: str
    data: bytes
    description: str | None
    """What a model said the image shows. None until it has been looked at, or if it could
    not be."""


def as_read(body: str, descriptions: Sequence[str | None]) -> str:
    """A message as the models are given it: its words, then what each attached image was
    taken to show. A description is a model's reading, and is labelled as one."""
    parts = [body] if body.strip() else []
    for number, description in enumerate(descriptions, start=1):
        if description is None:
            parts.append(f"[Attached image {number} could not be looked at.]")
        else:
            parts.append(
                f"[Attached image {number}, as described by a model that looked at it (the "
                f"description may be wrong): {description}]"
            )
    return "\n\n".join(parts)


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
