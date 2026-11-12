"""Behaviours pinned down after the milestone 1a independent review."""

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
    JobStatus,
    LeadOrigin,
    Report,
    SearchEngine,
    Stance,
)
from manyminds.core.storage import NotFoundError, Store
from support import RecordingModel, report_for

TEXT = "The bridge opened in 1932."


def a_report() -> Report:
    return report_for("Lead")


# -- storage: a failed write must not poison the connection ---------------------------------


def test_finishing_a_job_that_does_not_exist_is_refused(store: Store) -> None:
    with pytest.raises(NotFoundError):
        store.mark_job_done("no-such-job", a_report())


def test_the_store_keeps_working_after_a_refused_write(tmp_path: Path) -> None:
    path = tmp_path / "manyminds.db"
    store = Store(path)
    with pytest.raises(NotFoundError):
        store.mark_job_done("no-such-job", a_report())

    check = store.create_check(title="A", source_text="a", instructions="")
    thread = store.launch_lead(store.add_lead(check.id, "Lead", LeadOrigin.GENERATED).id)
    job = store.create_job(
        thread.id, model="vendor/model", search_engine=SearchEngine.AUTO, instructions=""
    )
    store.mark_job_running(job.id)
    store.mark_job_done(job.id, a_report())
    store.close()

    reopened = Store(path)
    try:
        assert reopened.list_checks() == [check]
        assert reopened.get_job(job.id).status is JobStatus.DONE
        assert reopened.get_report(job.id) == a_report()
    finally:
        reopened.close()


def test_a_write_that_fails_halfway_leaves_nothing_behind(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = store.create_check(title="A", source_text="a", instructions="")
    thread = store.launch_lead(store.add_lead(check.id, "Lead", LeadOrigin.GENERATED).id)
    job = store.create_job(
        thread.id, model="vendor/model", search_engine=SearchEngine.AUTO, instructions=""
    )
    store.mark_job_running(job.id)
    broken = a_report()
    monkeypatch.setattr(
        Report, "model_dump_json", lambda self, **_: (_ for _ in ()).throw(sqlite3.Error("disk"))
    )

    with pytest.raises(sqlite3.Error):
        store.mark_job_done(job.id, broken)
    monkeypatch.undo()

    assert store.get_job(job.id).status is JobStatus.RUNNING
    assert store.get_report(job.id) is None
    assert store.mark_job_done(job.id, a_report()).status is JobStatus.DONE


# -- storage: launched leads are frozen -----------------------------------------------------


def launched_thread(store: Store) -> tuple[str, str, str]:
    check = store.create_check(title="A", source_text="a", instructions="")
    lead = store.add_lead(check.id, "Original wording", LeadOrigin.GENERATED)
    thread = store.launch_lead(lead.id)
    job = store.create_job(
        thread.id, model="vendor/model", search_engine=SearchEngine.AUTO, instructions=""
    )
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


# -- jobs: a failure anywhere in a job ends it as failed -------------------------------------


async def test_a_storage_failure_while_finishing_fails_only_that_job(
    service: CheckService,
    store: Store,
    model: RecordingModel,
    jobs: JobManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model.leads = ["Unlucky lead", "Lucky lead"]
    check = await service.create_check(TEXT)
    real = store.mark_job_done

    def flaky(job_id: str, report: Report) -> Any:
        if report.summary == "Findings about: Unlucky lead":
            raise sqlite3.OperationalError("disk is full")
        return real(job_id, report)

    monkeypatch.setattr(store, "mark_job_done", flaky)
    unlucky, lucky = service.launch(check.id, ["vendor/model"])
    await jobs.wait_until_idle()

    (failed,) = store.list_jobs(unlucky.id)
    assert failed.status is JobStatus.FAILED
    assert failed.error_kind is ErrorKind.UNKNOWN
    assert failed.error_message == "Unexpected error (OperationalError)"
    (done,) = store.list_jobs(lucky.id)
    assert done.status is JobStatus.DONE


async def test_a_storage_failure_while_starting_fails_only_that_job(
    service: CheckService,
    store: Store,
    model: RecordingModel,
    jobs: JobManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model.leads = ["Unlucky lead", "Lucky lead"]
    check = await service.create_check(TEXT)
    unlucky, lucky = service.launch(check.id, ["vendor/model"])
    (unlucky_job,) = store.list_jobs(unlucky.id)
    real = store.mark_job_running

    def flaky(job_id: str) -> Any:
        if job_id == unlucky_job.id:
            raise sqlite3.OperationalError("database is locked")
        return real(job_id)

    monkeypatch.setattr(store, "mark_job_running", flaky)
    await jobs.wait_until_idle()

    assert store.get_job(unlucky_job.id).status is JobStatus.FAILED
    assert store.get_job(unlucky_job.id).error_kind is ErrorKind.UNKNOWN
    (done,) = store.list_jobs(lucky.id)
    assert done.status is JobStatus.DONE
    assert [call["lead"] for call in model.research_calls] == ["Lucky lead"]


async def test_no_job_error_goes_unhandled(
    service: CheckService,
    store: Store,
    model: RecordingModel,
    jobs: JobManager,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    check = await service.create_check(TEXT)
    monkeypatch.setattr(
        store, "mark_job_done", lambda *_: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    threads = service.launch(check.id, ["vendor/model"])

    with caplog.at_level(logging.ERROR, logger="asyncio"):
        await jobs.wait_until_idle()

    assert all(store.list_jobs(t.id)[0].status is JobStatus.FAILED for t in threads)
    assert "never retrieved" not in caplog.text


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
        service.launch(check.id, ["vendor/model"])
        await jobs.wait_until_idle()

    assert "RuntimeError" in caplog.text
    assert "sk-or-v1-SECRET" not in caplog.text


# -- checks and models ----------------------------------------------------------------------


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


def quote_of(length: int) -> dict[str, Any]:
    return {"url": "https://example.org/a", "quote": "q" * length, "stance": Stance.SUPPORTS}


def test_a_quote_may_be_two_thousand_characters() -> None:
    assert len(EvidenceItem.model_validate(quote_of(2000)).quote) == 2000


def test_a_longer_quote_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(quote_of(2001))
