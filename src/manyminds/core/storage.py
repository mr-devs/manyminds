"""SQLite storage for checks and everything that follows from them."""

import sqlite3
import threading
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
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
    Usage,
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
    "ALTER TABLE jobs ADD COLUMN usage TEXT;",
)


class NotFoundError(LookupError):
    """The requested record does not exist."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Store:
    """All persistence. Calls are short and safe to make from any thread.

    Every write runs in a transaction that is rolled back if anything in it fails, so a
    failure never leaves half a change behind or the connection unusable.
    """

    def __init__(
        self,
        path: Path | str,
        *,
        now: Callable[[], datetime] = _utc_now,
        connection_factory: type[sqlite3.Connection] = sqlite3.Connection,
    ) -> None:
        self._now = now
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            str(path), check_same_thread=False, isolation_level=None, factory=connection_factory
        )
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

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Several statements that take effect together or not at all."""
        with self._lock:
            self._db.execute("BEGIN")
            try:
                yield self._db
                self._db.execute("COMMIT")
            except BaseException:
                # Also reached when COMMIT itself fails, which leaves the transaction open.
                if self._db.in_transaction:
                    self._db.rollback()
                raise

    def _write(self, sql: str, parameters: Sequence[Any]) -> int:
        """Run one write in its own transaction and return how many rows it changed."""
        with self._transaction() as db:
            return db.execute(sql, parameters).rowcount

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
        return self.create_check_with_leads(
            title=title, source_text=source_text, instructions=instructions, leads=[]
        )

    def create_check_with_leads(
        self, *, title: str, source_text: str, instructions: str, leads: Sequence[str]
    ) -> Check:
        """Save a check and its generated leads together, or not at all."""
        check_id, stamp = uuid.uuid4().hex, self._stamp()
        with self._transaction() as db:
            db.execute(
                "INSERT INTO checks (id, title, source_text, instructions, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (check_id, title, source_text, instructions, stamp, stamp),
            )
            for text in leads:
                self._insert_lead(db, check_id, text, LeadOrigin.GENERATED)
        return self.get_check(check_id)

    def get_check(self, check_id: str) -> Check:
        row = self._one("SELECT * FROM checks WHERE id = ?", (check_id,), f"check {check_id}")
        return Check.model_validate(dict(row))

    def list_checks(self) -> list[Check]:
        rows = self._all("SELECT * FROM checks ORDER BY created_at DESC, rowid DESC")
        return [Check.model_validate(dict(row)) for row in rows]

    def delete_check(self, check_id: str) -> None:
        """Remove a check and everything under it: leads, threads, jobs, transcripts, reports."""
        if not self._write("DELETE FROM checks WHERE id = ?", (check_id,)):
            raise NotFoundError(f"check {check_id}")

    # -- leads ------------------------------------------------------------------------

    def add_lead(self, check_id: str, text: str, origin: LeadOrigin) -> Lead:
        with self._transaction() as db:
            lead_id = self._insert_lead(db, check_id, text, origin)
        return self._get_lead(lead_id)

    def _insert_lead(
        self, db: sqlite3.Connection, check_id: str, text: str, origin: LeadOrigin
    ) -> str:
        lead_id = uuid.uuid4().hex
        (position,) = db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM leads WHERE check_id = ?", (check_id,)
        ).fetchone()
        db.execute(
            "INSERT INTO leads (id, check_id, text, position, origin, state, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (lead_id, check_id, text, position, origin, LeadState.DRAFT, self._stamp()),
        )
        return lead_id

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
        """Reword a draft lead. A launched lead is frozen."""
        changed = self._write(
            "UPDATE leads SET text = ? WHERE id = ? AND state = ?", (text, lead_id, LeadState.DRAFT)
        )
        if not changed:
            raise NotFoundError(f"draft lead {lead_id}")

    def remove_lead(self, lead_id: str) -> None:
        """Delete a draft lead. A launched lead, and the research under it, stays."""
        changed = self._write(
            "DELETE FROM leads WHERE id = ? AND state = ?", (lead_id, LeadState.DRAFT)
        )
        if not changed:
            raise NotFoundError(f"draft lead {lead_id}")

    # -- threads ----------------------------------------------------------------------

    def launch_lead(self, lead_id: str) -> Thread:
        with self._transaction() as db:
            thread_id = self._launch(db, self._get_lead(lead_id))
        return self.get_thread(thread_id)

    def _launch(self, db: sqlite3.Connection, lead: Lead) -> str:
        if lead.state is not LeadState.DRAFT:
            raise NotFoundError(f"draft lead {lead.id}")
        thread_id = uuid.uuid4().hex
        db.execute("UPDATE leads SET state = ? WHERE id = ?", (LeadState.LAUNCHED, lead.id))
        db.execute(
            "INSERT INTO threads (id, check_id, lead_id, lead_text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (thread_id, lead.check_id, lead.id, lead.text, self._stamp()),
        )
        return thread_id

    def launch_leads(
        self,
        check_id: str,
        *,
        models: Sequence[str],
        search_engine: SearchEngine,
        instructions: str,
    ) -> tuple[list[Thread], list[Job]]:
        """Turn every draft lead into a thread with one queued job per model, all or nothing."""
        thread_ids: list[str] = []
        job_ids: list[str] = []
        with self._transaction() as db:
            for lead in self.list_draft_leads(check_id):
                thread_id = self._launch(db, lead)
                thread_ids.append(thread_id)
                job_ids += [
                    self._insert_job(db, thread_id, model, search_engine, instructions)
                    for model in models
                ]
        return (
            [self.get_thread(thread_id) for thread_id in thread_ids],
            [self.get_job(job_id) for job_id in job_ids],
        )

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
        self,
        thread_id: str,
        *,
        model: str,
        search_engine: SearchEngine,
        instructions: str,
        attempt: int = 1,
    ) -> Job:
        with self._transaction() as db:
            job_id = self._insert_job(db, thread_id, model, search_engine, instructions, attempt)
        return self.get_job(job_id)

    def _insert_job(
        self,
        db: sqlite3.Connection,
        thread_id: str,
        model: str,
        search_engine: SearchEngine,
        instructions: str,
        attempt: int = 1,
    ) -> str:
        job_id = uuid.uuid4().hex
        db.execute(
            "INSERT INTO jobs "
            "(id, thread_id, model, status, search_engine, instructions, attempt, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                thread_id,
                model,
                JobStatus.QUEUED,
                search_engine,
                instructions,
                attempt,
                self._stamp(),
            ),
        )
        return job_id

    def get_job(self, job_id: str) -> Job:
        row = self._one("SELECT * FROM jobs WHERE id = ?", (job_id,), f"job {job_id}")
        return _job(row)

    def list_jobs(self, thread_id: str) -> list[Job]:
        rows = self._all(
            "SELECT * FROM jobs WHERE thread_id = ? ORDER BY created_at, rowid", (thread_id,)
        )
        return [_job(row) for row in rows]

    def mark_job_running(self, job_id: str) -> Job:
        self._write(
            "UPDATE jobs SET status = ?, started_at = ? WHERE id = ?",
            (JobStatus.RUNNING, self._stamp(), job_id),
        )
        return self.get_job(job_id)

    def mark_job_done(self, job_id: str, report: Report, usage: Usage | None = None) -> Job:
        stamp = self._stamp()
        with self._transaction() as db:
            self.get_job(job_id)
            db.execute(
                "INSERT OR REPLACE INTO reports (job_id, body, created_at) VALUES (?, ?, ?)",
                (job_id, report.model_dump_json(), stamp),
            )
            db.execute(
                "UPDATE jobs SET status = ?, finished_at = ?, usage = ? WHERE id = ?",
                (JobStatus.DONE, stamp, usage.model_dump_json() if usage else None, job_id),
            )
        return self.get_job(job_id)

    def mark_job_failed(self, job_id: str, kind: ErrorKind, message: str) -> Job:
        """Record a failure. A job that already finished stays finished."""
        self._write(
            "UPDATE jobs SET status = ?, error_kind = ?, error_message = ?, finished_at = ? "
            "WHERE id = ? AND status != ?",
            (JobStatus.FAILED, kind, message, self._stamp(), job_id, JobStatus.DONE),
        )
        return self.get_job(job_id)

    def interrupt_unfinished_jobs(self) -> int:
        """Mark every job that was waiting or running as stopped. Call once, at start-up.

        Nothing is running when the app has only just started, so any such job was cut off
        when the app last closed. It is left for the user to try again.
        """
        message = "Stopped because the app was closed."
        stamp = self._now()
        with self._transaction() as db:
            rows = db.execute(
                "SELECT id FROM jobs WHERE status IN (?, ?)", (JobStatus.QUEUED, JobStatus.RUNNING)
            ).fetchall()
            db.execute(
                "UPDATE jobs SET status = ?, error_kind = ?, error_message = ?, finished_at = ? "
                "WHERE status IN (?, ?)",
                (
                    JobStatus.FAILED,
                    ErrorKind.INTERRUPTED,
                    message,
                    self._stamp(),
                    JobStatus.QUEUED,
                    JobStatus.RUNNING,
                ),
            )
            for row in rows:
                self._insert_event(db, row["id"], JobEventKind.FAILED, message, stamp)
        return len(rows)

    def count_unfinished_jobs(self, check_id: str) -> int:
        """How many of a check's jobs are still waiting or running."""
        rows = self._all(
            "SELECT COUNT(*) AS n FROM jobs JOIN threads ON threads.id = jobs.thread_id "
            "WHERE threads.check_id = ? AND jobs.status IN (?, ?)",
            (check_id, JobStatus.QUEUED, JobStatus.RUNNING),
        )
        return int(rows[0]["n"])

    def get_report(self, job_id: str) -> Report | None:
        rows = self._all("SELECT body FROM reports WHERE job_id = ?", (job_id,))
        return Report.model_validate_json(rows[0]["body"]) if rows else None

    # -- job events -------------------------------------------------------------------

    def add_job_event(self, job_id: str, kind: JobEventKind, detail: str = "") -> JobEvent:
        stamp = self._now()
        with self._transaction() as db:
            seq = self._insert_event(db, job_id, kind, detail, stamp)
        return JobEvent(job_id=job_id, seq=seq, kind=kind, detail=detail, created_at=stamp)

    def _insert_event(
        self,
        db: sqlite3.Connection,
        job_id: str,
        kind: JobEventKind,
        detail: str,
        stamp: datetime,
    ) -> int:
        (seq,) = db.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM job_events WHERE job_id = ?", (job_id,)
        ).fetchone()
        db.execute(
            "INSERT INTO job_events (job_id, seq, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, seq, kind, detail, stamp.isoformat()),
        )
        return int(seq)

    def list_job_events(self, job_id: str, *, after: int = 0) -> list[JobEvent]:
        """A job's transcript in order, optionally only the entries numbered above `after`."""
        rows = self._all(
            "SELECT * FROM job_events WHERE job_id = ? AND seq > ? ORDER BY seq", (job_id, after)
        )
        return [JobEvent.model_validate(dict(row)) for row in rows]


def _job(row: sqlite3.Row) -> Job:
    fields = dict(row)
    raw = fields.pop("usage")
    return Job.model_validate({**fields, "usage": Usage.model_validate_json(raw) if raw else None})
