"""What a job consumed is saved with it and shown on the thread."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from manyminds.core import storage
from manyminds.core.models import JobStatus, SearchEngine, Usage
from manyminds.core.services import build_services
from manyminds.core.storage import Store
from support import RecordingModel, report_for

USAGE = Usage(input_tokens=6772, output_tokens=1096, cost=0.00901378, searches=2)


def launched_job(store: Store) -> str:
    check = store.create_check_with_leads(
        title="A title", source_text="Some text.", instructions="", leads=["Lead A"]
    )
    _, jobs = store.launch_leads(
        check.id, models=["vendor/model-a"], search_engine=SearchEngine.EXA, instructions=""
    )
    return jobs[0].id


def test_a_finished_job_keeps_its_usage(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite")
    job_id = launched_job(store)

    store.mark_job_done(job_id, report_for("Lead A"), USAGE)
    store.close()

    reopened = Store(tmp_path / "db.sqlite")
    job = reopened.get_job(job_id)
    assert job.status is JobStatus.DONE
    assert job.usage == Usage(input_tokens=6772, output_tokens=1096, cost=0.00901378, searches=2)
    assert reopened.list_jobs(job.thread_id)[0].usage == job.usage
    reopened.close()


def test_a_job_has_no_usage_until_it_finishes(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite")

    job = store.get_job(launched_job(store))

    assert job.usage is None
    store.close()


def test_a_version_one_database_is_upgraded_and_keeps_its_jobs(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    with sqlite3.connect(path) as raw:
        raw.executescript(f"BEGIN; {storage.MIGRATIONS[0]} PRAGMA user_version = 1; COMMIT;")
        raw.execute(
            "INSERT INTO checks (id, title, source_text, instructions, created_at, updated_at) "
            "VALUES ('c1', 'T', 'text', '', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z')"
        )
        raw.execute(
            "INSERT INTO leads (id, check_id, text, position, origin, state, created_at) "
            "VALUES ('l1', 'c1', 'Lead A', 0, 'generated', 'launched', '2026-11-01T00:00:00Z')"
        )
        raw.execute(
            "INSERT INTO threads (id, check_id, lead_id, lead_text, created_at) "
            "VALUES ('t1', 'c1', 'l1', 'Lead A', '2026-11-01T00:00:00Z')"
        )
        raw.execute(
            "INSERT INTO jobs (id, thread_id, model, status, search_engine, instructions, attempt, "
            "created_at) VALUES ('j1', 't1', 'vendor/model-a', 'queued', 'auto', '', 1, "
            "'2026-11-01T00:00:00Z')"
        )
    raw.close()

    store = Store(path)

    old = store.get_job("j1")
    assert old.usage is None
    assert old.search_engine is SearchEngine.AUTO
    done = store.mark_job_done("j1", report_for("Lead A"), USAGE)
    assert done.usage == USAGE
    store.close()
    with sqlite3.connect(path) as check:
        assert check.execute("PRAGMA user_version").fetchone() == (4,)


async def test_the_job_runner_saves_what_the_model_reports() -> None:
    model = RecordingModel(leads=["Lead A", "Lead B"], usages={"Lead A": USAGE})
    services = build_services(
        store=Store(":memory:"),
        model=model,
        research_models=["vendor/model-a"],
        decompose_model="vendor/fast-model",
    )
    check = await services.checks.create_check("Some text.")
    services.checks.launch(check.id, models=["vendor/model-a"])
    await services.jobs.wait_until_idle()

    by_lead = {
        thread.lead_text: services.store.list_jobs(thread.id)[0]
        for thread in services.store.list_threads(check.id)
    }
    assert by_lead["Lead A"].usage == USAGE
    assert by_lead["Lead B"].usage == Usage(input_tokens=0, output_tokens=0, cost=0.0, searches=0)


async def test_new_jobs_search_with_exa_unless_told_otherwise() -> None:
    services = build_services(
        store=Store(":memory:"),
        model=RecordingModel(leads=["Lead A"]),
        research_models=["vendor/model-a"],
        decompose_model="vendor/fast-model",
    )
    check = await services.checks.create_check("Some text.")
    services.checks.launch(check.id, models=["vendor/model-a"])
    await services.jobs.wait_until_idle()

    thread = services.store.list_threads(check.id)[0]
    assert services.store.list_jobs(thread.id)[0].search_engine is SearchEngine.EXA
