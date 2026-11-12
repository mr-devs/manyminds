"""SQLite storage for checks and everything that follows from them."""

import sqlite3
import threading
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from manyminds.core.models import (
    Check,
    ErrorKind,
    Job,
    JobEvent,
    JobEventKind,
    JobStatus,
    Lead,
    LeadOrigin,
    LeadState,
    Report,
    SearchEngine,
    Thread,
)

# Each entry moves the schema forward by one version. Never edit an entry that has shipped;
# append a new one.
MIGRATIONS: Sequence[str] = (
    """
    CREATE TABLE checks (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        source_text TEXT NOT NULL,
        instructions TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE leads (
        id TEXT PRIMARY KEY,
        check_id TEXT NOT NULL REFERENCES checks(id) ON DELETE CASCADE,
        text TEXT NOT NULL,
        position INTEGER NOT NULL,
        origin TEXT NOT NULL,
        state TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE threads (
        id TEXT PRIMARY KEY,
        check_id TEXT NOT NULL REFERENCES checks(id) ON DELETE CASCADE,
        lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        lead_text TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE jobs (
        id TEXT PRIMARY KEY,
        thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
        model TEXT NOT NULL,
        status TEXT NOT NULL,
        search_engine TEXT NOT NULL,
        instructions TEXT NOT NULL,
        attempt INTEGER NOT NULL,
        error_kind TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT
    );
    CREATE TABLE job_events (
        job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        seq INTEGER NOT NULL,
        kind TEXT NOT NULL,
        detail TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (job_id, seq)
    );
    CREATE TABLE reports (
        job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
)


class NotFoundError(LookupError):
    """The requested record does not exist."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Store:
    """All persistence. Calls are short and safe to make from any thread."""

    def __init__(self, path: Path | str, *, now: Callable[[], datetime] = _utc_now) -> None:
        self._now = now
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def close(self) -> None:
        self._db.close()

    # -- plumbing ---------------------------------------------------------------------

    def _migrate(self) -> None:
        with self._lock:
            (version,) = self._db.execute("PRAGMA user_version").fetchone()
            for index in range(version, len(MIGRATIONS)):
                self._db.executescript(
                    f"BEGIN; {MIGRATIONS[index]} PRAGMA user_version = {index + 1}; COMMIT;"
                )

    def _execute(self, sql: str, parameters: Sequence[Any] = ()) -> None:
        with self._lock:
            self._db.execute(sql, parameters)

    def _all(self, sql: str, parameters: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, parameters).fetchall()

    def _one(self, sql: str, parameters: Sequence[Any], what: str) -> sqlite3.Row:
        rows = self._all(sql, parameters)
        if not rows:
            raise NotFoundError(what)
        return rows[0]

    def _stamp(self) -> str:
        return self._now().isoformat()

    # -- checks -----------------------------------------------------------------------

    def create_check(self, *, title: str, source_text: str, instructions: str) -> Check:
        check_id, stamp = uuid.uuid4().hex, self._stamp()
        self._execute(
            "INSERT INTO checks VALUES (?, ?, ?, ?, ?, ?)",
            (check_id, title, source_text, instructions, stamp, stamp),
        )
        return self.get_check(check_id)

    def get_check(self, check_id: str) -> Check:
        row = self._one("SELECT * FROM checks WHERE id = ?", (check_id,), f"check {check_id}")
        return Check.model_validate(dict(row))

    def list_checks(self) -> list[Check]:
        rows = self._all("SELECT * FROM checks ORDER BY created_at DESC, rowid DESC")
        return [Check.model_validate(dict(row)) for row in rows]

    # -- leads ------------------------------------------------------------------------

    def add_lead(self, check_id: str, text: str, origin: LeadOrigin) -> Lead:
        lead_id = uuid.uuid4().hex
        with self._lock:
            (position,) = self._db.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM leads WHERE check_id = ?", (check_id,)
            ).fetchone()
            self._db.execute(
                "INSERT INTO leads VALUES (?, ?, ?, ?, ?, ?, ?)",
                (lead_id, check_id, text, position, origin, LeadState.DRAFT, self._stamp()),
            )
        return self._get_lead(lead_id)

    def _get_lead(self, lead_id: str) -> Lead:
        row = self._one("SELECT * FROM leads WHERE id = ?", (lead_id,), f"lead {lead_id}")
        return Lead.model_validate(dict(row))

    def list_draft_leads(self, check_id: str) -> list[Lead]:
        rows = self._all(
            "SELECT * FROM leads WHERE check_id = ? AND state = ? ORDER BY position",
            (check_id, LeadState.DRAFT),
        )
        return [Lead.model_validate(dict(row)) for row in rows]

    def update_lead_text(self, lead_id: str, text: str) -> None:
        self._execute("UPDATE leads SET text = ? WHERE id = ?", (text, lead_id))

    def remove_lead(self, lead_id: str) -> None:
        self._execute("DELETE FROM leads WHERE id = ?", (lead_id,))

    # -- threads ----------------------------------------------------------------------

    def launch_lead(self, lead_id: str) -> Thread:
        lead = self._get_lead(lead_id)
        thread_id = uuid.uuid4().hex
        with self._lock:
            self._db.execute("BEGIN")
            self._db.execute(
                "UPDATE leads SET state = ? WHERE id = ?", (LeadState.LAUNCHED, lead_id)
            )
            self._db.execute(
                "INSERT INTO threads VALUES (?, ?, ?, ?, ?)",
                (thread_id, lead.check_id, lead.id, lead.text, self._stamp()),
            )
            self._db.execute("COMMIT")
        return self.get_thread(thread_id)

    def get_thread(self, thread_id: str) -> Thread:
        row = self._one("SELECT * FROM threads WHERE id = ?", (thread_id,), f"thread {thread_id}")
        return Thread.model_validate(dict(row))

    def list_threads(self, check_id: str) -> list[Thread]:
        rows = self._all(
            "SELECT * FROM threads WHERE check_id = ? ORDER BY created_at, rowid", (check_id,)
        )
        return [Thread.model_validate(dict(row)) for row in rows]

    # -- jobs -------------------------------------------------------------------------

    def create_job(
        self, thread_id: str, *, model: str, search_engine: SearchEngine, instructions: str
    ) -> Job:
        job_id = uuid.uuid4().hex
        self._execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, 1, NULL, NULL, ?, NULL, NULL)",
            (
                job_id,
                thread_id,
                model,
                JobStatus.QUEUED,
                search_engine,
                instructions,
                self._stamp(),
            ),
        )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Job:
        row = self._one("SELECT * FROM jobs WHERE id = ?", (job_id,), f"job {job_id}")
        return Job.model_validate(dict(row))

    def list_jobs(self, thread_id: str) -> list[Job]:
        rows = self._all(
            "SELECT * FROM jobs WHERE thread_id = ? ORDER BY created_at, rowid", (thread_id,)
        )
        return [Job.model_validate(dict(row)) for row in rows]

    def mark_job_running(self, job_id: str) -> Job:
        self._execute(
            "UPDATE jobs SET status = ?, started_at = ? WHERE id = ?",
            (JobStatus.RUNNING, self._stamp(), job_id),
        )
        return self.get_job(job_id)

    def mark_job_done(self, job_id: str, report: Report) -> Job:
        stamp = self._stamp()
        with self._lock:
            self._db.execute("BEGIN")
            self._db.execute(
                "INSERT OR REPLACE INTO reports VALUES (?, ?, ?)",
                (job_id, report.model_dump_json(), stamp),
            )
            self._db.execute(
                "UPDATE jobs SET status = ?, finished_at = ? WHERE id = ?",
                (JobStatus.DONE, stamp, job_id),
            )
            self._db.execute("COMMIT")
        return self.get_job(job_id)

    def mark_job_failed(self, job_id: str, kind: ErrorKind, message: str) -> Job:
        self._execute(
            "UPDATE jobs SET status = ?, error_kind = ?, error_message = ?, finished_at = ? "
            "WHERE id = ?",
            (JobStatus.FAILED, kind, message, self._stamp(), job_id),
        )
        return self.get_job(job_id)

    def get_report(self, job_id: str) -> Report | None:
        rows = self._all("SELECT body FROM reports WHERE job_id = ?", (job_id,))
        return Report.model_validate_json(rows[0]["body"]) if rows else None

    # -- job events -------------------------------------------------------------------

    def add_job_event(self, job_id: str, kind: JobEventKind, detail: str = "") -> JobEvent:
        with self._lock:
            (seq,) = self._db.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM job_events WHERE job_id = ?", (job_id,)
            ).fetchone()
            self._db.execute(
                "INSERT INTO job_events VALUES (?, ?, ?, ?, ?)",
                (job_id, seq, kind, detail, self._stamp()),
            )
        return self.list_job_events(job_id)[-1]

    def list_job_events(self, job_id: str) -> list[JobEvent]:
        rows = self._all("SELECT * FROM job_events WHERE job_id = ? ORDER BY seq", (job_id,))
        return [JobEvent.model_validate(dict(row)) for row in rows]
