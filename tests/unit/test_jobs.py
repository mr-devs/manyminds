"""Research jobs: concurrent, isolated from each other, and persisted as they progress."""

from manyminds.core.checks import CheckService
from manyminds.core.errors import ModelError
from manyminds.core.events import ChatUpdated, EventBus, JobUpdated, Update
from manyminds.core.jobs import JobManager
from manyminds.core.models import (
    ErrorKind,
    Job,
    JobEventKind,
    JobStatus,
    SearchEngine,
    Thread,
    ThreadStatus,
)
from manyminds.core.storage import Store
from support import RecordingModel, report_for, until

TEXT = "The bridge opened in 1932."
MODEL = "vendor/research-model"


async def launched(service: CheckService, model: RecordingModel, *leads: str) -> list[Thread]:
    model.leads = list(leads)
    check = await service.create_check(TEXT, "Prefer archives")
    return service.launch(check.id, [MODEL])


def job_of(store: Store, thread: Thread) -> Job:
    (job,) = store.list_jobs(thread.id)
    return job


async def test_jobs_run_to_completion_and_store_their_reports(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    threads = await launched(service, model, "Lead A", "Lead B")

    await jobs.wait_until_idle()

    for thread in threads:
        job = job_of(store, thread)
        assert job.status is JobStatus.DONE
        assert job.started_at is not None
        assert job.finished_at is not None
        assert job.started_at <= job.finished_at
        assert store.get_report(job.id) == report_for(thread.lead_text)


async def test_research_receives_the_lead_the_text_and_the_job_settings(
    service: CheckService, model: RecordingModel, jobs: JobManager
) -> None:
    await launched(service, model, "Lead A")

    await jobs.wait_until_idle()

    assert model.research_calls == [
        {
            "lead": "Lead A",
            "source_text": TEXT,
            "instructions": "Prefer archives",
            "model": MODEL,
            "search": SearchEngine.AUTO,
        }
    ]


async def test_no_more_than_the_limit_run_at_once(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.hold = True
    threads = await launched(service, model, "A", "B", "C", "D", "E")

    await until(lambda: model.active == 2)
    statuses = sorted(job_of(store, thread).status for thread in threads)
    assert statuses == [JobStatus.QUEUED] * 3 + [JobStatus.RUNNING] * 2

    model.release_all()
    await jobs.wait_until_idle()

    assert model.max_active == 2
    assert len(model.research_calls) == 5
    assert all(job_of(store, thread).status is JobStatus.DONE for thread in threads)


async def test_jobs_really_overlap(
    service: CheckService, model: RecordingModel, jobs: JobManager
) -> None:
    model.hold = True
    await launched(service, model, "A", "B")

    await until(lambda: model.active == 2)

    assert [call["lead"] for call in model.research_calls] == ["A", "B"]
    model.release_all()
    await jobs.wait_until_idle()


async def test_a_finished_report_is_readable_while_another_job_is_still_running(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.hold = True
    fast, slow = await launched(service, model, "Fast lead", "Slow lead")

    model.release("Fast lead")
    await until(lambda: job_of(store, fast).status is JobStatus.DONE)

    assert store.get_report(job_of(store, fast).id) == report_for("Fast lead")
    assert job_of(store, slow).status is JobStatus.RUNNING
    assert store.get_report(job_of(store, slow).id) is None
    model.release_all()
    await jobs.wait_until_idle()


async def test_one_failing_job_does_not_affect_the_others(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.failures = {"Bad lead": ModelError(ErrorKind.RATE_LIMIT, "Too many requests")}
    good_one, bad, good_two = await launched(service, model, "Good one", "Bad lead", "Good two")

    await jobs.wait_until_idle()

    failed = job_of(store, bad)
    assert failed.status is JobStatus.FAILED
    assert failed.error_kind is ErrorKind.RATE_LIMIT
    assert failed.error_message == "Too many requests"
    assert failed.finished_at is not None
    assert store.get_report(failed.id) is None
    for thread in (good_one, good_two):
        job = job_of(store, thread)
        assert job.status is JobStatus.DONE
        assert store.get_report(job.id) == report_for(thread.lead_text)


async def test_an_unexpected_error_fails_only_that_job_and_hides_its_details(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.failures = {"Bad lead": RuntimeError("boom with key sk-or-v1-SECRET")}
    bad, good = await launched(service, model, "Bad lead", "Good lead")

    await jobs.wait_until_idle()

    failed = job_of(store, bad)
    assert failed.status is JobStatus.FAILED
    assert failed.error_kind is ErrorKind.UNKNOWN
    assert failed.error_message == "Unexpected error (RuntimeError)"
    assert job_of(store, good).status is JobStatus.DONE


async def test_progress_is_recorded_in_order(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    (thread,) = await launched(service, model, "Lead A")

    await jobs.wait_until_idle()

    events = store.list_job_events(job_of(store, thread).id)
    assert [(event.kind, event.detail) for event in events] == [
        (JobEventKind.STARTED, ""),
        (JobEventKind.SEARCHING, "query for Lead A"),
        (JobEventKind.FINISHED, ""),
    ]


async def test_a_failed_job_ends_with_a_failed_event(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.failures = {"Lead A": ModelError(ErrorKind.TIMEOUT, "Timed out")}
    (thread,) = await launched(service, model, "Lead A")

    await jobs.wait_until_idle()

    events = store.list_job_events(job_of(store, thread).id)
    assert (events[-1].kind, events[-1].detail) == (JobEventKind.FAILED, "Timed out")


async def test_every_status_change_is_saved_before_it_is_announced(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager, bus: EventBus
) -> None:
    seen: list[tuple[str, JobStatus]] = []

    def record(event: Update) -> None:
        assert isinstance(event, JobUpdated)
        seen.append((event.job_id, store.get_job(event.job_id).status))

    bus.subscribe(record)
    (thread,) = await launched(service, model, "Lead A")
    job_id = job_of(store, thread).id

    await jobs.wait_until_idle()

    assert all(seen_id == job_id for seen_id, _ in seen)
    statuses = [status for _, status in seen]
    assert statuses[0] is JobStatus.RUNNING
    assert statuses[-1] is JobStatus.DONE
    assert statuses == sorted(statuses, key=[JobStatus.RUNNING, JobStatus.DONE].index)


async def test_announcements_say_which_check_and_thread_changed(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager, bus: EventBus
) -> None:
    events: list[Update] = []
    bus.subscribe(events.append)
    (thread,) = await launched(service, model, "Lead A")

    await jobs.wait_until_idle()

    assert {
        (event.check_id, event.thread_id) for event in events if isinstance(event, JobUpdated)
    } == {(thread.check_id, thread.id)}
    # The job ending is also announced to the check's conversation.
    assert ChatUpdated(check_id=thread.check_id) in events


async def test_unsubscribed_listeners_hear_nothing_more(
    service: CheckService, model: RecordingModel, jobs: JobManager, bus: EventBus
) -> None:
    events: list[Update] = []
    unsubscribe = bus.subscribe(events.append)
    unsubscribe()

    await launched(service, model, "Lead A")
    await jobs.wait_until_idle()

    assert events == []


async def test_a_broken_listener_does_not_break_the_job(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager, bus: EventBus
) -> None:
    def broken(event: Update) -> None:
        raise RuntimeError("listener bug")

    heard: list[Update] = []
    bus.subscribe(broken)
    bus.subscribe(heard.append)
    (thread,) = await launched(service, model, "Lead A")

    await jobs.wait_until_idle()

    assert job_of(store, thread).status is JobStatus.DONE
    assert len(heard) >= 2


async def test_thread_status_follows_its_job(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.hold = True
    model.failures = {"C": ModelError(ErrorKind.PROVIDER, "Upstream error")}
    a, b, c = await launched(service, model, "A", "B", "C")

    assert service.thread_status(c.id) is ThreadStatus.QUEUED
    await until(lambda: model.active == 2)
    assert service.thread_status(a.id) is ThreadStatus.WORKING
    assert service.thread_status(c.id) is ThreadStatus.QUEUED

    model.release_all()
    await jobs.wait_until_idle()

    assert service.thread_status(a.id) is ThreadStatus.FINISHED
    assert service.thread_status(b.id) is ThreadStatus.FINISHED
    assert service.thread_status(c.id) is ThreadStatus.FAILED
