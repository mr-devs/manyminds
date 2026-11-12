"""Behaviour pinned after the independent review of milestone 1c."""

from __future__ import annotations

import sqlite3
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from manyminds import cli
from manyminds.core.checks import CheckBusyError
from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind, JobEventKind, JobStatus, ThreadStatus
from manyminds.core.paths import AlreadyRunningError, hold_instance_lock, open_store
from manyminds.core.services import Services, build_services
from manyminds.core.storage import Store
from manyminds.ui.theme import format_when
from support import Faults, RecordingModel, flaky_connection, report_for

KEY = "sk-or-v1-cli-test-key-0123456789-do-not-print"


def services_on(store: Store, model: RecordingModel) -> Services:
    return build_services(
        store=store,
        model=model,
        research_models=["vendor/model-a"],
        decompose_model="vendor/fast-model",
    )


# -- dates ---------------------------------------------------------------------------------


def test_dates_are_written_without_a_leading_zero_on_any_platform() -> None:
    assert format_when(datetime(2026, 11, 3, 9, 5)) == "3 Nov 2026, 09:05"
    assert format_when(datetime(2026, 1, 21, 17, 40)) == "21 Jan 2026, 17:40"


# -- the data folder -----------------------------------------------------------------------


def test_an_existing_folder_keeps_its_own_permissions(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)

    open_store(shared).close()

    assert stat.S_IMODE(shared.stat().st_mode) == 0o755
    assert stat.S_IMODE((shared / "manyminds.db").stat().st_mode) == 0o600


def test_only_the_folder_the_app_creates_is_made_private(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o755)
    parent.chmod(0o755)

    open_store(parent / "manyminds").close()

    assert stat.S_IMODE(parent.stat().st_mode) == 0o755
    assert stat.S_IMODE((parent / "manyminds").stat().st_mode) == 0o700


def test_a_second_instance_on_the_same_folder_is_refused(tmp_path: Path) -> None:
    first = hold_instance_lock(tmp_path)

    with pytest.raises(AlreadyRunningError):
        hold_instance_lock(tmp_path)

    first.close()
    hold_instance_lock(tmp_path).close()


# -- starting up -----------------------------------------------------------------------------


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_run(services: Services, **options: Any) -> None:
        captured["services"] = services

    monkeypatch.setattr("manyminds.ui.app.run", fake_run)
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    monkeypatch.setenv("MANYMINDS_DATA_DIR", str(tmp_path / "data"))
    return captured


def test_a_data_folder_that_is_really_a_file_is_explained(
    served: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "data").write_text("not a folder")

    status = cli.main([])

    error = capsys.readouterr().err
    assert status == 1
    assert served == {}
    assert str(tmp_path / "data") in error
    assert "MANYMINDS_DATA_DIR" in error
    assert "Traceback" not in error


def test_a_database_that_cannot_be_read_is_explained(
    served: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "manyminds.db").write_bytes(b"this is not a database at all" * 50)

    status = cli.main([])

    error = capsys.readouterr().err
    assert status == 1
    assert served == {}
    assert "manyminds.db" in error


def test_starting_twice_on_one_folder_is_refused_and_changes_nothing(
    served: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from manyminds.core.models import SearchEngine

    earlier = open_store(tmp_path / "data")
    check = earlier.create_check_with_leads(
        title="T", source_text="Some text.", instructions="", leads=["Lead A"]
    )
    _, jobs = earlier.launch_leads(
        check.id, models=["vendor/model-a"], search_engine=SearchEngine.EXA, instructions=""
    )
    running = hold_instance_lock(tmp_path / "data")

    status = cli.main([])

    assert status == 1
    assert served == {}
    assert "already running" in capsys.readouterr().err
    assert earlier.get_job(jobs[0].id).status is JobStatus.QUEUED
    running.close()
    earlier.close()


# -- interruption ------------------------------------------------------------------------------


def test_interrupting_is_all_or_nothing(tmp_path: Path) -> None:
    from manyminds.core.models import SearchEngine

    faults = Faults()
    store = Store(tmp_path / "db.sqlite", connection_factory=flaky_connection(faults))
    check = store.create_check_with_leads(
        title="T", source_text="Some text.", instructions="", leads=["Lead A", "Lead B"]
    )
    _, jobs = store.launch_leads(
        check.id, models=["vendor/model-a"], search_engine=SearchEngine.EXA, instructions=""
    )
    faults.fail("INSERT INTO job_events")

    with pytest.raises(sqlite3.OperationalError, match="injected"):
        store.interrupt_unfinished_jobs()

    assert [store.get_job(job.id).status for job in jobs] == [JobStatus.QUEUED, JobStatus.QUEUED]
    assert [store.list_job_events(job.id) for job in jobs] == [[], []]
    store.close()


async def test_an_interrupted_thread_can_be_tried_again_and_keeps_its_old_transcript(
    tmp_path: Path,
) -> None:
    from manyminds.core.models import SearchEngine

    # The app was closed with this job still queued: nothing ever ran it.
    first = open_store(tmp_path)
    check = first.create_check_with_leads(
        title="T", source_text="Some text.", instructions="", leads=["Lead A"]
    )
    threads, _ = first.launch_leads(
        check.id, models=["vendor/model-a"], search_engine=SearchEngine.EXA, instructions=""
    )
    thread = threads[0]
    first.close()

    second = open_store(tmp_path)
    assert second.interrupt_unfinished_jobs() == 1
    again = services_on(second, RecordingModel(leads=["Lead A"]))
    assert again.checks.thread_status(thread.id) is ThreadStatus.FAILED
    again.checks.retry_thread(thread.id)
    await again.jobs.wait_until_idle()

    old, new = second.list_jobs(thread.id)
    assert (old.error_kind, new.status) == (ErrorKind.INTERRUPTED, JobStatus.DONE)
    assert second.list_job_events(old.id)[-1].kind is JobEventKind.FAILED
    assert second.get_report(new.id) == report_for("Lead A")
    assert again.checks.thread_status(thread.id) is ThreadStatus.FINISHED
    second.close()


async def test_a_thread_already_being_tried_again_is_not_started_twice() -> None:
    model = RecordingModel(
        leads=["Lead A"], failures={"Lead A": ModelError(ErrorKind.PROVIDER, "It broke.")}
    )
    running = services_on(Store(":memory:"), model)
    check = await running.checks.create_check("Some text.")
    thread = running.checks.launch(check.id, models=["vendor/model-a"])[0]
    await running.jobs.wait_until_idle()
    model.failures.clear()
    model.hold = True
    running.checks.retry_thread(thread.id)

    with pytest.raises(ValueError, match="has not failed"):
        running.checks.retry_thread(thread.id)

    model.release_all()
    await running.jobs.wait_until_idle()
    assert len(running.store.list_jobs(thread.id)) == 2


# -- deleting while work is under way -----------------------------------------------------------


async def test_a_check_with_research_under_way_cannot_be_deleted() -> None:
    model = RecordingModel(leads=["Lead A"], hold=True)
    running = services_on(Store(":memory:"), model)
    check = await running.checks.create_check("Some text.")
    running.checks.launch(check.id, models=["vendor/model-a"])

    with pytest.raises(CheckBusyError) as caught:
        running.checks.delete_check(check.id)

    assert str(caught.value) == "Research is still running. Wait for it to finish, then delete."
    assert running.store.get_check(check.id) == check
    model.release_all()
    await running.jobs.wait_until_idle()
    running.checks.delete_check(check.id)
    assert running.store.list_checks() == []


# -- titles --------------------------------------------------------------------------------------


async def test_a_very_long_title_from_the_model_is_shortened() -> None:
    model = RecordingModel(title="Word " * 80, leads=["Lead A"])
    running = services_on(Store(":memory:"), model)

    check = await running.checks.create_check("Some text.")

    assert len(check.title) <= 120
    assert check.title.startswith("Word Word Word")
    assert check.title.endswith("…")


async def test_a_title_spread_over_lines_becomes_one_line() -> None:
    model = RecordingModel(title="First line\n\nSecond   line", leads=["Lead A"])
    running = services_on(Store(":memory:"), model)

    check = await running.checks.create_check("Some text.")

    assert check.title == "First line Second line"
