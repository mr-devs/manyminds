"""Runs research jobs concurrently and records their progress."""

import asyncio
import logging

from manyminds.core.errors import ModelError
from manyminds.core.events import EventBus, JobUpdated
from manyminds.core.models import ErrorKind, JobEventKind
from manyminds.core.ports import ModelClient, Progress
from manyminds.core.storage import Store

logger = logging.getLogger(__name__)


class JobManager:
    """Each job runs in its own task; a failure in one never reaches another."""

    def __init__(
        self, store: Store, model: ModelClient, bus: EventBus, *, max_concurrent: int = 6
    ) -> None:
        self._store = store
        self._model = model
        self._bus = bus
        self._slots = asyncio.Semaphore(max_concurrent)
        self._tasks: set[asyncio.Task[None]] = set()

    def start(self, job_id: str) -> None:
        """Schedule a queued job. Must be called from the running event loop."""
        task = asyncio.get_running_loop().create_task(self._run(job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def wait_until_idle(self) -> None:
        while self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            # Waiting on tasks that have already finished does not hand control back to the
            # event loop, and they are only forgotten once it runs their callbacks.
            await asyncio.sleep(0)

    async def _run(self, job_id: str) -> None:
        """Run one job to an end state. Nothing that goes wrong here may escape the task."""
        try:
            await self._research(job_id)
        except Exception as error:
            # The text of an unexpected error may contain anything, so it is logged by type
            # only and never stored or shown.
            name = type(error).__name__
            logger.error("Job %s failed unexpectedly: %s", job_id, name)
            self._fail(job_id, ErrorKind.UNKNOWN, f"Unexpected error ({name})")

    async def _research(self, job_id: str) -> None:
        job = self._store.get_job(job_id)
        thread = self._store.get_thread(job.thread_id)
        check = self._store.get_check(thread.check_id)
        update = JobUpdated(check_id=check.id, thread_id=thread.id, job_id=job_id)

        def record(progress: Progress) -> None:
            self._store.add_job_event(job_id, progress.kind, progress.detail)
            self._bus.publish(update)

        async with self._slots:
            self._store.mark_job_running(job_id)
            record(Progress(JobEventKind.STARTED))
            try:
                result = await self._model.research(
                    thread.lead_text,
                    self._store.source_for_lead(thread.lead_id),
                    job.instructions,
                    model=job.model,
                    search=job.search_engine,
                    on_progress=record,
                )
            except ModelError as error:
                self._fail(job_id, error.kind, error.message)
                return
            self._store.mark_job_done(job_id, result.report, result.usage)
        # The job is finished and saved. Announcing that must not be able to undo it.
        try:
            record(Progress(JobEventKind.FINISHED))
        except Exception as error:
            logger.error(
                "Job %s finished but could not record it: %s", job_id, type(error).__name__
            )
            self._bus.publish(update)

    def _fail(self, job_id: str, kind: ErrorKind, message: str) -> None:
        try:
            job = self._store.mark_job_failed(job_id, kind, message)
            thread = self._store.get_thread(job.thread_id)
            self._store.add_job_event(job_id, JobEventKind.FAILED, message)
            self._bus.publish(
                JobUpdated(check_id=thread.check_id, thread_id=thread.id, job_id=job_id)
            )
        except Exception as error:
            logger.error("Job %s could not be marked as failed: %s", job_id, type(error).__name__)
