"""SQLite storage: everything a check produces is saved and survives reopening the file."""

import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from manyminds.core.models import (
    ErrorKind,
    EvidenceItem,
    JobEventKind,
    JobStatus,
    LeadOrigin,
    LeadState,
    Report,
    SearchEngine,
    Stance,
)
from manyminds.core.storage import NotFoundError, Store

START = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def ticking_clock() -> Callable[[], datetime]:
    """Each call returns a time one second after the previous one."""
    ticks = iter(range(10_000))
    return lambda: START + timedelta(seconds=next(ticks))


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "manyminds.db"


@pytest.fixture
def store(db_path: Path) -> Iterator[Store]:
    opened = Store(db_path, now=ticking_clock())
    yield opened
    opened.close()


def sample_report() -> Report:
    return Report(
        summary="One archive gives the date.",
        evidence=[
            EvidenceItem(
                url="https://example.org/a",
                title="Archive",
                quote="Opened in 1932.",
                stance=Stance.SUPPORTS,
                grounded=True,
                quote_matched=True,
            ),
            EvidenceItem(
                url="https://example.net/b",
                quote="Records from that year are missing.",
                stance=Stance.UNDERMINES,
            ),
        ],
        undetermined="The exact day.",
    )


def test_new_database_is_at_the_latest_schema_version(store: Store, db_path: Path) -> None:
    with sqlite3.connect(db_path) as raw:
        assert raw.execute("PRAGMA user_version").fetchone() == (2,)


def test_check_round_trip(store: Store) -> None:
    created = store.create_check(
        title="Bridge claim", source_text="The bridge opened in 1932.", instructions="Use archives"
    )

    loaded = store.get_check(created.id)

    assert loaded == created
    assert loaded.title == "Bridge claim"
    assert loaded.source_text == "The bridge opened in 1932."
    assert loaded.instructions == "Use archives"
    assert loaded.created_at == START
    assert loaded.updated_at == START


def test_ids_are_unique(store: Store) -> None:
    first = store.create_check(title="A", source_text="a", instructions="")
    second = store.create_check(title="B", source_text="b", instructions="")

    assert first.id != second.id


def test_missing_check_raises_not_found(store: Store) -> None:
    with pytest.raises(NotFoundError):
        store.get_check("no-such-id")


def test_checks_are_listed_newest_first(store: Store) -> None:
    older = store.create_check(title="Older", source_text="a", instructions="")
    newer = store.create_check(title="Newer", source_text="b", instructions="")

    assert [check.id for check in store.list_checks()] == [newer.id, older.id]


def test_leads_keep_their_order_and_start_as_drafts(store: Store) -> None:
    check = store.create_check(title="A", source_text="a", instructions="")
    first = store.add_lead(check.id, "When did it open?", LeadOrigin.GENERATED)
    second = store.add_lead(check.id, "Who built it?", LeadOrigin.MANUAL)

    leads = store.list_draft_leads(check.id)

    assert [lead.id for lead in leads] == [first.id, second.id]
    assert [lead.text for lead in leads] == ["When did it open?", "Who built it?"]
    assert [lead.position for lead in leads] == [0, 1]
    assert [lead.origin for lead in leads] == [LeadOrigin.GENERATED, LeadOrigin.MANUAL]
    assert all(lead.state is LeadState.DRAFT for lead in leads)
    assert all(lead.check_id == check.id for lead in leads)


def test_leads_belong_to_their_own_check(store: Store) -> None:
    one = store.create_check(title="A", source_text="a", instructions="")
    two = store.create_check(title="B", source_text="b", instructions="")
    store.add_lead(one.id, "Lead for one", LeadOrigin.GENERATED)

    assert store.list_draft_leads(two.id) == []


def test_lead_text_can_be_edited(store: Store) -> None:
    check = store.create_check(title="A", source_text="a", instructions="")
    lead = store.add_lead(check.id, "Original", LeadOrigin.GENERATED)

    store.update_lead_text(lead.id, "Edited")

    assert [item.text for item in store.list_draft_leads(check.id)] == ["Edited"]


def test_removed_lead_is_gone_and_others_stay_in_order(store: Store) -> None:
    check = store.create_check(title="A", source_text="a", instructions="")
    first = store.add_lead(check.id, "One", LeadOrigin.GENERATED)
    second = store.add_lead(check.id, "Two", LeadOrigin.GENERATED)
    third = store.add_lead(check.id, "Three", LeadOrigin.GENERATED)

    store.remove_lead(second.id)

    assert [lead.id for lead in store.list_draft_leads(check.id)] == [first.id, third.id]


def test_launching_a_lead_creates_a_thread_with_a_frozen_copy_of_the_text(store: Store) -> None:
    check = store.create_check(title="A", source_text="a", instructions="")
    lead = store.add_lead(check.id, "When did it open?", LeadOrigin.GENERATED)

    thread = store.launch_lead(lead.id)

    assert thread.check_id == check.id
    assert thread.lead_id == lead.id
    assert thread.lead_text == "When did it open?"
    assert store.get_thread(thread.id) == thread
    assert store.list_threads(check.id) == [thread]
    assert store.list_draft_leads(check.id) == []


def test_new_job_is_queued_on_its_first_attempt(store: Store) -> None:
    check = store.create_check(title="A", source_text="a", instructions="")
    thread = store.launch_lead(store.add_lead(check.id, "Lead", LeadOrigin.GENERATED).id)

    job = store.create_job(
        thread.id, model="vendor/model-a", search_engine=SearchEngine.EXA, instructions="Be brief"
    )

    assert job.thread_id == thread.id
    assert job.model == "vendor/model-a"
    assert job.search_engine is SearchEngine.EXA
    assert job.instructions == "Be brief"
    assert job.status is JobStatus.QUEUED
    assert job.attempt == 1
    assert job.started_at is None
    assert job.finished_at is None
    assert job.error_kind is None
    assert job.error_message is None
    assert store.get_job(job.id) == job
    assert store.list_jobs(thread.id) == [job]


def make_job(store: Store) -> str:
    check = store.create_check(title="A", source_text="a", instructions="")
    thread = store.launch_lead(store.add_lead(check.id, "Lead", LeadOrigin.GENERATED).id)
    job = store.create_job(
        thread.id, model="vendor/model-a", search_engine=SearchEngine.AUTO, instructions=""
    )
    return job.id


def test_running_job_records_when_it_started(store: Store) -> None:
    job_id = make_job(store)

    running = store.mark_job_running(job_id)

    assert running.status is JobStatus.RUNNING
    assert running.started_at is not None
    assert running.finished_at is None
    assert store.get_job(job_id) == running


def test_finished_job_stores_its_report(store: Store) -> None:
    job_id = make_job(store)
    store.mark_job_running(job_id)

    done = store.mark_job_done(job_id, sample_report())

    assert done.status is JobStatus.DONE
    assert done.finished_at is not None
    assert store.get_report(job_id) == sample_report()


def test_job_without_a_report_has_none(store: Store) -> None:
    job_id = make_job(store)

    assert store.get_report(job_id) is None


def test_failed_job_records_kind_and_message(store: Store) -> None:
    job_id = make_job(store)
    store.mark_job_running(job_id)

    failed = store.mark_job_failed(job_id, ErrorKind.RATE_LIMIT, "Too many requests")

    assert failed.status is JobStatus.FAILED
    assert failed.error_kind is ErrorKind.RATE_LIMIT
    assert failed.error_message == "Too many requests"
    assert failed.finished_at is not None
    assert store.get_report(job_id) is None


def test_job_events_are_numbered_in_order(store: Store) -> None:
    job_id = make_job(store)

    store.add_job_event(job_id, JobEventKind.STARTED)
    store.add_job_event(job_id, JobEventKind.SEARCHING, "bridge opening date")
    store.add_job_event(job_id, JobEventKind.FINISHED)

    events = store.list_job_events(job_id)
    assert [event.seq for event in events] == [1, 2, 3]
    assert [event.kind for event in events] == [
        JobEventKind.STARTED,
        JobEventKind.SEARCHING,
        JobEventKind.FINISHED,
    ]
    assert [event.detail for event in events] == ["", "bridge opening date", ""]
    assert all(event.job_id == job_id for event in events)


def test_everything_survives_closing_and_reopening(db_path: Path) -> None:
    first = Store(db_path, now=ticking_clock())
    check = first.create_check(title="A", source_text="pasted text", instructions="notes")
    draft = first.add_lead(check.id, "Still a draft", LeadOrigin.MANUAL)
    thread = first.launch_lead(first.add_lead(check.id, "Launched", LeadOrigin.GENERATED).id)
    job = first.create_job(
        thread.id, model="vendor/model-a", search_engine=SearchEngine.AUTO, instructions="notes"
    )
    first.mark_job_running(job.id)
    first.add_job_event(job.id, JobEventKind.SEARCHING, "query")
    finished = first.mark_job_done(job.id, sample_report())
    first.close()

    second = Store(db_path)
    try:
        assert second.list_checks() == [check]
        assert second.list_draft_leads(check.id) == [draft]
        assert second.list_threads(check.id) == [thread]
        assert second.list_jobs(thread.id) == [finished]
        assert second.get_report(job.id) == sample_report()
        assert [event.detail for event in second.list_job_events(job.id)] == ["query"]
    finally:
        second.close()


def test_reopening_does_not_reapply_migrations(db_path: Path) -> None:
    Store(db_path).close()
    Store(db_path).close()

    with sqlite3.connect(db_path) as raw:
        assert raw.execute("PRAGMA user_version").fetchone() == (2,)


def test_the_database_never_contains_a_verdict_column(store: Store, db_path: Path) -> None:
    with sqlite3.connect(db_path) as raw:
        schema = " ".join(row[0] for row in raw.execute("SELECT sql FROM sqlite_master") if row[0])

    assert "verdict" not in schema.lower()
    assert "confidence" not in schema.lower()
