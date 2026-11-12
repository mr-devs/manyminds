"""Behaviours pinned down after independent reviews of milestone 1a.

Storage failures are injected at the SQLite connection, the real boundary, through the
`faults` fixture.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from manyminds.core.checks import CheckService
from manyminds.core.errors import ModelError
from manyminds.core.jobs import JobManager
from manyminds.core.models import (
    ErrorKind,
    EvidenceItem,
    Job,
    JobEventKind,
    JobStatus,
    LeadOrigin,
    Report,
    SearchEngine,
    Stance,
    Thread,
)
from manyminds.core.storage import NotFoundError, Store
from support import Faults, RecordingModel, flaky_connection, report_for

TEXT = "The bridge opened in 1932."
MODEL = "vendor/model"


def a_report() -> Report:
    return report_for("Lead")


def running_job(store: Store) -> Job:
    check = store.create_check(title="A", source_text="a", instructions="")
    thread = store.launch_lead(store.add_lead(check.id, "Lead", LeadOrigin.GENERATED).id)
    job = store.create_job(thread.id, model=MODEL, search_engine=SearchEngine.AUTO, instructions="")
    return store.mark_job_running(job.id)


def only_job(store: Store, thread: Thread) -> Job:
    (job,) = store.list_jobs(thread.id)
    return job


# -- storage: failed writes ------------------------------------------------------------------


def test_finishing_a_job_that_does_not_exist_is_refused(store: Store) -> None:
    with pytest.raises(NotFoundError):
        store.mark_job_done("no-such-job", a_report())


def test_a_write_that_fails_halfway_leaves_nothing_behind(store: Store, faults: Faults) -> None:
    job = running_job(store)
    faults.fail("UPDATE jobs", param=JobStatus.DONE)

    with pytest.raises(sqlite3.OperationalError):
        store.mark_job_done(job.id, a_report())

    assert store.get_job(job.id).status is JobStatus.RUNNING
    assert store.get_report(job.id) is None
    assert store.mark_job_done(job.id, a_report()).status is JobStatus.DONE
    assert store.get_report(job.id) == a_report()


def test_a_failed_commit_does_not_leave_the_store_stuck(tmp_path: Path) -> None:
    path = tmp_path / "manyminds.db"
    faults = Faults()
    store = Store(path, connection_factory=flaky_connection(faults))
    check = store.create_check(title="A", source_text="a", instructions="")
    lead = store.add_lead(check.id, "Lead", LeadOrigin.GENERATED)
    faults.fail("COMMIT")

    with pytest.raises(sqlite3.OperationalError):
        store.launch_lead(lead.id)

    assert store.list_threads(check.id) == []
    assert store.list_draft_leads(check.id) == [lead]
    thread = store.launch_lead(lead.id)
    job = store.create_job(thread.id, model=MODEL, search_engine=SearchEngine.AUTO, instructions="")
    store.close()

    reopened = Store(path)
    try:
        assert reopened.list_threads(check.id) == [thread]
        assert reopened.list_jobs(thread.id) == [job]
    finally:
        reopened.close()


def test_a_finished_job_cannot_be_marked_failed(store: Store) -> None:
    job = running_job(store)
    store.mark_job_done(job.id, a_report())

    after = store.mark_job_failed(job.id, ErrorKind.UNKNOWN, "late failure")

    assert after.status is JobStatus.DONE
    assert after.error_kind is None
    assert after.error_message is None
    assert store.get_report(job.id) == a_report()


@pytest.mark.parametrize("table", ["checks", "leads", "threads", "jobs", "job_events", "reports"])
def test_a_column_added_later_does_not_break_writes(tmp_path: Path, table: str) -> None:
    path = tmp_path / "manyminds.db"
    Store(path).close()
    with sqlite3.connect(path) as raw:
        raw.execute(f"ALTER TABLE {table} ADD COLUMN added_later TEXT")

    store = Store(path)
    try:
        check = store.create_check_with_leads(
            title="A", source_text="a", instructions="", leads=["One", "Two"]
        )
        store.add_lead(check.id, "Three", LeadOrigin.MANUAL)
        threads, jobs = store.launch_leads(
            check.id, models=[MODEL], search_engine=SearchEngine.AUTO, instructions=""
        )
        store.mark_job_running(jobs[0].id)
        store.add_job_event(jobs[0].id, JobEventKind.STARTED)
        store.mark_job_done(jobs[0].id, a_report())
        store.mark_job_failed(jobs[1].id, ErrorKind.TIMEOUT, "Timed out")

        assert len(threads) == 3
        assert store.get_report(jobs[0].id) == a_report()
        assert store.get_job(jobs[1].id).status is JobStatus.FAILED
    finally:
        store.close()


# -- storage: launched leads are frozen ------------------------------------------------------


def launched_thread(store: Store) -> tuple[str, str, str]:
    check = store.create_check(title="A", source_text="a", instructions="")
    lead = store.add_lead(check.id, "Original wording", LeadOrigin.GENERATED)
    thread = store.launch_lead(lead.id)
    job = store.create_job(thread.id, model=MODEL, search_engine=SearchEngine.AUTO, instructions="")
    return lead.id, thread.id, job.id


def test_a_launched_lead_cannot_be_removed(store: Store) -> None:
    lead_id, thread_id, job_id = launched_thread(store)

    with pytest.raises(NotFoundError):
        store.remove_lead(lead_id)

    assert store.get_thread(thread_id).lead_text == "Original wording"
    assert store.get_job(job_id).status is JobStatus.QUEUED


def test_a_launched_lead_cannot_be_edited(store: Store) -> None:
    lead_id, thread_id, _ = launched_thread(store)

    with pytest.raises(NotFoundError):
        store.update_lead_text(lead_id, "Rewritten")

    assert store.get_thread(thread_id).lead_text == "Original wording"


def test_a_lead_cannot_be_launched_twice(store: Store) -> None:
    lead_id, _, _ = launched_thread(store)

    with pytest.raises(NotFoundError):
        store.launch_lead(lead_id)


def test_removing_a_lead_that_does_not_exist_is_refused(store: Store) -> None:
    with pytest.raises(NotFoundError):
        store.remove_lead("no-such-lead")


# -- storage: several records written together ----------------------------------------------


def test_a_check_and_its_leads_are_saved_together(store: Store) -> None:
    check = store.create_check_with_leads(
        title="A", source_text="a", instructions="notes", leads=["One", "Two"]
    )

    assert store.get_check(check.id) == check
    leads = store.list_draft_leads(check.id)
    assert [(lead.text, lead.position, lead.origin) for lead in leads] == [
        ("One", 0, LeadOrigin.GENERATED),
        ("Two", 1, LeadOrigin.GENERATED),
    ]


def test_a_check_is_not_saved_if_one_of_its_leads_cannot_be(store: Store, faults: Faults) -> None:
    faults.fail("INTO leads", skip=1)

    with pytest.raises(sqlite3.OperationalError):
        store.create_check_with_leads(
            title="A", source_text="a", instructions="", leads=["One", "Two", "Three"]
        )

    assert store.list_checks() == []


def test_launching_creates_every_thread_and_job_together(store: Store) -> None:
    check = store.create_check_with_leads(
        title="A", source_text="a", instructions="", leads=["One", "Two"]
    )

    threads, jobs = store.launch_leads(
        check.id,
        models=["vendor/a", "vendor/b"],
        search_engine=SearchEngine.EXA,
        instructions="notes",
    )

    assert [thread.lead_text for thread in threads] == ["One", "Two"]
    assert store.list_threads(check.id) == threads
    assert store.list_draft_leads(check.id) == []
    assert [(job.thread_id, job.model) for job in jobs] == [
        (threads[0].id, "vendor/a"),
        (threads[0].id, "vendor/b"),
        (threads[1].id, "vendor/a"),
        (threads[1].id, "vendor/b"),
    ]
    assert all(job.status is JobStatus.QUEUED for job in jobs)
    assert all(job.search_engine is SearchEngine.EXA for job in jobs)
    assert all(job.instructions == "notes" for job in jobs)


def test_a_launch_that_fails_partway_changes_nothing(store: Store, faults: Faults) -> None:
    check = store.create_check_with_leads(
        title="A", source_text="a", instructions="", leads=["One", "Two"]
    )
    drafts = store.list_draft_leads(check.id)
    faults.fail("INTO jobs", skip=1)

    with pytest.raises(sqlite3.OperationalError):
        store.launch_leads(
            check.id, models=[MODEL], search_engine=SearchEngine.AUTO, instructions=""
        )

    assert store.list_threads(check.id) == []
    assert store.list_draft_leads(check.id) == drafts


def test_transcript_entries_can_be_read_from_a_point_onwards(store: Store) -> None:
    job = running_job(store)
    store.add_job_event(job.id, JobEventKind.STARTED)
    store.add_job_event(job.id, JobEventKind.SEARCHING, "first")
    store.add_job_event(job.id, JobEventKind.SEARCHING, "second")

    later = store.list_job_events(job.id, after=1)

    assert [(event.seq, event.detail) for event in later] == [(2, "first"), (3, "second")]
    assert store.list_job_events(job.id, after=3) == []
    assert len(store.list_job_events(job.id)) == 3


def test_adding_a_transcript_entry_returns_it(store: Store) -> None:
    job = running_job(store)
    store.add_job_event(job.id, JobEventKind.STARTED)

    added = store.add_job_event(job.id, JobEventKind.THINKING, "some thoughts")

    assert (added.job_id, added.seq, added.kind, added.detail) == (
        job.id,
        2,
        JobEventKind.THINKING,
        "some thoughts",
    )
    assert store.list_job_events(job.id)[-1] == added


# -- jobs: a failure anywhere in a job ends it properly --------------------------------------


async def launch_two(service: CheckService, model: RecordingModel) -> list[Thread]:
    model.leads = ["First lead", "Second lead"]
    check = await service.create_check(TEXT)
    return service.launch(check.id, [MODEL])


async def test_a_storage_failure_while_finishing_fails_only_that_job(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager, faults: Faults
) -> None:
    threads = await launch_two(service, model)
    faults.fail("INTO reports")

    await jobs.wait_until_idle()

    outcomes = sorted(only_job(store, thread).status for thread in threads)
    assert outcomes == [JobStatus.DONE, JobStatus.FAILED]
    (failed,) = [
        job for thread in threads if (job := only_job(store, thread)).status is JobStatus.FAILED
    ]
    assert failed.error_kind is ErrorKind.UNKNOWN
    assert failed.error_message == "Unexpected error (OperationalError)"
    assert store.get_report(failed.id) is None


async def test_a_storage_failure_while_starting_fails_only_that_job(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager, faults: Faults
) -> None:
    threads = await launch_two(service, model)
    faults.fail("UPDATE jobs", param=JobStatus.RUNNING)

    await jobs.wait_until_idle()

    first, second = (only_job(store, thread) for thread in threads)
    assert first.status is JobStatus.FAILED
    assert first.error_kind is ErrorKind.UNKNOWN
    assert second.status is JobStatus.DONE
    assert [call["lead"] for call in model.research_calls] == ["Second lead"]


async def test_no_job_error_goes_unhandled(
    service: CheckService,
    store: Store,
    model: RecordingModel,
    jobs: JobManager,
    faults: Faults,
    caplog: pytest.LogCaptureFixture,
) -> None:
    threads = await launch_two(service, model)
    faults.fail("INTO reports", times=None)

    with caplog.at_level(logging.ERROR, logger="asyncio"):
        await jobs.wait_until_idle()

    assert all(only_job(store, thread).status is JobStatus.FAILED for thread in threads)
    assert "never retrieved" not in caplog.text


async def test_a_failure_after_the_report_is_saved_does_not_undo_the_job(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager, faults: Faults
) -> None:
    threads = await launch_two(service, model)
    faults.fail("INTO job_events", param=JobEventKind.FINISHED, times=None)

    await jobs.wait_until_idle()

    for thread in threads:
        job = only_job(store, thread)
        assert job.status is JobStatus.DONE
        assert job.error_kind is None
        assert store.get_report(job.id) == report_for(thread.lead_text)


async def test_unexpected_error_text_never_reaches_the_log(
    service: CheckService,
    model: RecordingModel,
    jobs: JobManager,
    caplog: pytest.LogCaptureFixture,
) -> None:
    model.leads = ["Bad lead"]
    model.failures = {"Bad lead": RuntimeError("boom with key sk-or-v1-SECRET")}
    check = await service.create_check(TEXT)

    with caplog.at_level(logging.DEBUG):
        service.launch(check.id, [MODEL])
        await jobs.wait_until_idle()

    assert "RuntimeError" in caplog.text
    assert "sk-or-v1-SECRET" not in caplog.text


# -- checks and models -----------------------------------------------------------------------


@pytest.mark.parametrize("leads", [[], ["", "   "]])
async def test_no_usable_leads_is_an_error_and_saves_nothing(
    service: CheckService, store: Store, model: RecordingModel, leads: list[str]
) -> None:
    model.leads = leads

    with pytest.raises(ModelError) as raised:
        await service.create_check(TEXT)

    assert raised.value.kind is ErrorKind.INVALID_OUTPUT
    assert raised.value.message == "No leads could be generated for this text."
    assert store.list_checks() == []


async def test_a_check_that_cannot_be_fully_saved_is_not_saved_at_all(
    service: CheckService, store: Store, model: RecordingModel, faults: Faults
) -> None:
    model.leads = ["One", "Two", "Three"]
    faults.fail("INTO leads", skip=2)

    with pytest.raises(sqlite3.OperationalError):
        await service.create_check(TEXT)

    assert store.list_checks() == []


async def test_a_launch_that_cannot_be_fully_saved_starts_nothing(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager, faults: Faults
) -> None:
    model.leads = ["One", "Two"]
    check = await service.create_check(TEXT)
    faults.fail("INTO jobs", skip=1)

    with pytest.raises(sqlite3.OperationalError):
        service.launch(check.id, [MODEL])
    await jobs.wait_until_idle()

    assert store.list_threads(check.id) == []
    assert [lead.text for lead in store.list_draft_leads(check.id)] == ["One", "Two"]
    assert model.research_calls == []


def quote_of(length: int) -> dict[str, Any]:
    return {"url": "https://example.org/a", "quote": "q" * length, "stance": Stance.SUPPORTS}


def test_a_quote_may_be_two_thousand_characters() -> None:
    assert len(EvidenceItem.model_validate(quote_of(2000)).quote) == 2000


def test_a_longer_quote_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(quote_of(2001))
