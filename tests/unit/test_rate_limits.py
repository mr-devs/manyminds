"""A research job that is told to slow down waits and tries again, a limited number of times."""

from manyminds.core.checks import CheckService
from manyminds.core.errors import ModelError
from manyminds.core.events import EventBus
from manyminds.core.jobs import JobManager
from manyminds.core.models import ErrorKind, JobEventKind, JobStatus, SearchEngine
from manyminds.core.storage import Store
from support import RecordingModel, report_for

TEXT = "The bridge opened in 1932."
MODEL = "vendor/research-model"
LIMITED = "OpenRouter is limiting requests right now: 20 requests per minute for this model."


def limited(retry_after: float | None = None) -> ModelError:
    return ModelError(ErrorKind.RATE_LIMIT, LIMITED, retry_after=retry_after)


class Pauses:
    """Stands in for the clock: records each wait and returns at once."""

    def __init__(self) -> None:
        self.waited: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waited.append(seconds)


def service_with(store: Store, model: RecordingModel, jobs: JobManager) -> CheckService:
    return CheckService(
        store,
        model,
        jobs,
        bus=EventBus(),
        decompose_model="vendor/fast-model",
        chat_model="vendor/chat-model",
        search_engine=SearchEngine.AUTO,
    )


async def run_one_lead(store: Store, model: RecordingModel, pauses: Pauses) -> str:
    """Research "Lead A" to its end and return the job's id."""
    jobs = JobManager(store, model, EventBus(), sleep=pauses)
    service = service_with(store, model, jobs)
    model.leads = ["Lead A"]
    check = await service.create_check(TEXT)
    (thread,) = service.launch(check.id, [MODEL])
    await jobs.wait_until_idle()
    (job,) = store.list_jobs(thread.id)
    return job.id


async def test_a_rate_limited_job_waits_a_minute_and_tries_again(
    store: Store, model: RecordingModel
) -> None:
    model.fail_first["Lead A"] = [limited()]
    pauses = Pauses()

    job_id = await run_one_lead(store, model, pauses)

    assert pauses.waited == [60.0]
    assert len(model.research_calls) == 2
    assert store.get_job(job_id).status is JobStatus.DONE
    assert store.get_report(job_id) == report_for("Lead A")


async def test_the_wait_is_recorded_in_the_transcript_with_the_reason(
    store: Store, model: RecordingModel
) -> None:
    model.fail_first["Lead A"] = [limited()]

    job_id = await run_one_lead(store, model, Pauses())

    steps = [(event.kind, event.detail) for event in store.list_job_events(job_id)]
    assert (JobEventKind.RETRYING, f"{LIMITED} Trying again in 60 seconds.") in steps
    assert steps[-1][0] is JobEventKind.FINISHED
    assert JobEventKind.FAILED not in [kind for kind, _ in steps]


async def test_the_wait_is_as_long_as_openrouter_asks_when_that_is_longer(
    store: Store, model: RecordingModel
) -> None:
    model.fail_first["Lead A"] = [limited(retry_after=90.0), limited(retry_after=5.0)]
    pauses = Pauses()

    await run_one_lead(store, model, pauses)

    assert pauses.waited == [90.0, 60.0]


async def test_a_job_still_limited_after_two_more_tries_fails_with_the_reason(
    store: Store, model: RecordingModel
) -> None:
    model.failures["Lead A"] = limited()
    pauses = Pauses()

    job_id = await run_one_lead(store, model, pauses)

    assert pauses.waited == [60.0, 60.0]
    assert len(model.research_calls) == 3
    job = store.get_job(job_id)
    assert job.status is JobStatus.FAILED
    assert job.error_kind is ErrorKind.RATE_LIMIT
    assert job.error_message == LIMITED


async def test_other_failures_are_not_tried_again(store: Store, model: RecordingModel) -> None:
    model.failures["Lead A"] = ModelError(ErrorKind.PROVIDER, "Upstream error")
    pauses = Pauses()

    job_id = await run_one_lead(store, model, pauses)

    assert pauses.waited == []
    assert len(model.research_calls) == 1
    assert store.get_job(job_id).status is JobStatus.FAILED


async def test_three_jobs_run_at_once_unless_told_otherwise(
    store: Store, model: RecordingModel
) -> None:
    jobs = JobManager(store, model, EventBus())
    service = service_with(store, model, jobs)
    model.leads = ["Lead A", "Lead B", "Lead C", "Lead D", "Lead E"]
    check = await service.create_check(TEXT)

    service.launch(check.id, [MODEL])
    await jobs.wait_until_idle()

    assert model.max_active == 3
