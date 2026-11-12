"""Checks are kept on this computer and survive a restart."""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import platformdirs
import pytest

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind, JobEventKind, JobStatus, SearchEngine, ThreadStatus
from manyminds.core.paths import data_dir, open_store
from manyminds.core.services import Services, build_services
from manyminds.core.storage import NotFoundError, Store
from support import RecordingModel, report_for


def services_on(store: Store, model: RecordingModel) -> Services:
    return build_services(
        store=store,
        model=model,
        research_models=["vendor/model-a"],
        decompose_model="vendor/fast-model",
    )


def launched(store: Store, leads: list[str]) -> list[str]:
    check = store.create_check_with_leads(
        title="A title", source_text="Some text.", instructions="", leads=leads
    )
    _, jobs = store.launch_leads(
        check.id, models=["vendor/model-a"], search_engine=SearchEngine.EXA, instructions=""
    )
    return [job.id for job in jobs]


# -- where the data lives ------------------------------------------------------------------


def test_the_data_folder_can_be_set_by_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MANYMINDS_DATA_DIR", str(tmp_path / "elsewhere"))

    assert data_dir() == tmp_path / "elsewhere"


@pytest.mark.parametrize("value", ["", "   "])
def test_the_data_folder_defaults_to_the_users_own_data_folder(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MANYMINDS_DATA_DIR", value)

    assert data_dir() == Path(platformdirs.user_data_dir("manyminds", appauthor=False))
    assert data_dir().is_absolute()


def test_opening_the_store_creates_a_private_folder_and_file(tmp_path: Path) -> None:
    folder = tmp_path / "new" / "manyminds"

    store = open_store(folder)
    store.close()

    database = folder / "manyminds.db"
    assert database.is_file()
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600


# -- surviving a restart -------------------------------------------------------------------


async def test_checks_threads_reports_and_transcripts_survive_a_restart(tmp_path: Path) -> None:
    first = open_store(tmp_path)
    running = services_on(first, RecordingModel(title="Bridge claim", leads=["Lead A"]))
    check = await running.checks.create_check("The bridge opened in 1932.")
    running.checks.launch(check.id, models=["vendor/model-a"])
    await running.jobs.wait_until_idle()
    first.close()

    second = open_store(tmp_path)

    assert [c.title for c in second.list_checks()] == ["Bridge claim"]
    thread = second.list_threads(check.id)[0]
    job = second.list_jobs(thread.id)[0]
    assert job.status is JobStatus.DONE
    assert second.get_report(job.id) == report_for("Lead A")
    assert [e.kind for e in second.list_job_events(job.id)] == [
        JobEventKind.STARTED,
        JobEventKind.SEARCHING,
        JobEventKind.FINISHED,
    ]
    second.close()


def test_work_cut_off_by_a_restart_is_marked_interrupted(tmp_path: Path) -> None:
    first = open_store(tmp_path)
    queued, running, done = launched(first, ["Lead A", "Lead B", "Lead C"])
    first.mark_job_running(running)
    first.mark_job_running(done)
    first.mark_job_done(done, report_for("Lead C"))
    first.close()

    second = open_store(tmp_path)
    count = second.interrupt_unfinished_jobs()

    assert count == 2
    for job_id in (queued, running):
        job = second.get_job(job_id)
        assert job.status is JobStatus.FAILED
        assert job.error_kind is ErrorKind.INTERRUPTED
        assert job.error_message == "Stopped because the app was closed."
        last = second.list_job_events(job_id)[-1]
        assert (last.kind, last.detail) == (
            JobEventKind.FAILED,
            "Stopped because the app was closed.",
        )
    assert second.get_job(done).status is JobStatus.DONE
    assert second.interrupt_unfinished_jobs() == 0
    second.close()


# -- deleting ------------------------------------------------------------------------------


async def test_deleting_a_check_removes_everything_under_it(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    running = services_on(store, RecordingModel(leads=["Lead A", "Lead B"]))
    doomed = await running.checks.create_check("First text.")
    kept = await running.checks.create_check("Second text.")
    running.checks.launch(doomed.id, models=["vendor/model-a"])
    running.checks.launch(kept.id, models=["vendor/model-a"])
    await running.jobs.wait_until_idle()

    running.checks.delete_check(doomed.id)
    store.close()

    with sqlite3.connect(tmp_path / "manyminds.db") as raw:
        counts = {
            table: raw.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in ("checks", "leads", "threads", "jobs", "job_events", "reports")
        }
        texts = [row[0] for row in raw.execute("SELECT source_text FROM checks")]
    assert counts == {
        "checks": 1,
        "leads": 2,
        "threads": 2,
        "jobs": 2,
        "job_events": 6,
        "reports": 2,
    }
    assert texts == ["Second text."]


def test_deleting_an_unknown_check_is_an_error(tmp_path: Path) -> None:
    store = open_store(tmp_path)

    with pytest.raises(NotFoundError):
        store.delete_check("no-such-check")
    store.close()


# -- trying a stopped thread again ---------------------------------------------------------


async def test_a_failed_thread_can_be_tried_again() -> None:
    model = RecordingModel(
        leads=["Lead A"], failures={"Lead A": ModelError(ErrorKind.PROVIDER, "It broke.")}
    )
    running = services_on(Store(":memory:"), model)
    check = await running.checks.create_check("Some text.")
    thread = running.checks.launch(check.id, models=["vendor/model-a"])[0]
    await running.jobs.wait_until_idle()
    assert running.checks.thread_status(thread.id) is ThreadStatus.FAILED

    model.failures.clear()
    running.checks.retry_thread(thread.id)
    await running.jobs.wait_until_idle()

    jobs = running.store.list_jobs(thread.id)
    assert [(job.status, job.attempt, job.model) for job in jobs] == [
        (JobStatus.FAILED, 1, "vendor/model-a"),
        (JobStatus.DONE, 2, "vendor/model-a"),
    ]
    assert jobs[1].search_engine is jobs[0].search_engine
    assert running.checks.thread_status(thread.id) is ThreadStatus.FINISHED
    assert running.store.get_report(jobs[1].id) == report_for("Lead A")


async def test_a_thread_that_did_not_fail_cannot_be_tried_again() -> None:
    running = services_on(Store(":memory:"), RecordingModel(leads=["Lead A"]))
    check = await running.checks.create_check("Some text.")
    thread = running.checks.launch(check.id, models=["vendor/model-a"])[0]
    await running.jobs.wait_until_idle()

    with pytest.raises(ValueError, match="has not failed"):
        running.checks.retry_thread(thread.id)

    assert len(running.store.list_jobs(thread.id)) == 1
