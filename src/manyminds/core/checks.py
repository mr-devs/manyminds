"""Use cases for a check: generate leads, edit them, launch research."""

from collections.abc import Sequence

from manyminds.core.errors import ModelError
from manyminds.core.jobs import JobManager
from manyminds.core.models import (
    Check,
    ErrorKind,
    Job,
    JobStatus,
    Lead,
    LeadOrigin,
    SearchEngine,
    Thread,
    ThreadStatus,
)
from manyminds.core.ports import ModelClient
from manyminds.core.storage import Store

INITIAL_LEADS = 10
MAX_LEADS = 25
"""The most leads waiting in one list. Launched leads no longer count."""
TITLE_LENGTH = 60


class NothingToLaunchError(ValueError):
    """There are no draft leads left, for example because another tab launched them."""


class TooManyLeadsError(ValueError):
    """The list of leads waiting to be researched is full."""


def _squash(text: str) -> str:
    return " ".join(text.split())


def _unique_leads(leads: Sequence[str], limit: int) -> list[str]:
    """Trim, drop blanks, and drop repeats that differ only in case or spacing."""
    seen: set[str] = set()
    kept: list[str] = []
    for lead in leads:
        text = lead.strip()
        key = _squash(text).casefold()
        if key and key not in seen:
            seen.add(key)
            kept.append(text)
    return kept[:limit]


def summarise(jobs: Sequence[Job]) -> ThreadStatus:
    statuses = {job.status for job in jobs}
    if JobStatus.RUNNING in statuses:
        return ThreadStatus.WORKING
    if JobStatus.QUEUED in statuses:
        return ThreadStatus.QUEUED
    if JobStatus.DONE in statuses:
        return ThreadStatus.FINISHED
    return ThreadStatus.FAILED


class CheckService:
    def __init__(
        self,
        store: Store,
        model: ModelClient,
        jobs: JobManager,
        *,
        decompose_model: str,
        search_engine: SearchEngine,
    ) -> None:
        self.store = store
        self.jobs = jobs
        self._model = model
        self._decompose_model = decompose_model
        self._search_engine = search_engine

    async def create_check(self, text: str, instructions: str = "") -> Check:
        """Generate leads for a pasted text and save both. Nothing is saved on failure."""
        if not text.strip():
            raise ValueError("The text to check is empty")
        decomposition = await self._model.decompose(
            text, instructions, count=INITIAL_LEADS, avoid=[], model=self._decompose_model
        )
        leads = _unique_leads(decomposition.leads, INITIAL_LEADS)
        if not leads:
            raise ModelError(ErrorKind.INVALID_OUTPUT, "No leads could be generated for this text.")
        title = decomposition.title.strip() or _squash(text)[:TITLE_LENGTH]
        return self.store.create_check_with_leads(
            title=title, source_text=text, instructions=instructions, leads=leads
        )

    def delete_check(self, check_id: str) -> None:
        self.store.delete_check(check_id)

    def add_lead(self, check_id: str) -> Lead:
        """Add an empty lead for the user to fill in."""
        if len(self.store.list_draft_leads(check_id)) >= MAX_LEADS:
            raise TooManyLeadsError(
                f"A list holds {MAX_LEADS} leads at most. Research these, then add the rest."
            )
        return self.store.add_lead(check_id, "", LeadOrigin.MANUAL)

    def update_lead(self, lead_id: str, text: str) -> None:
        """Save a draft lead's wording. It may be left empty, but then it cannot be launched."""
        self.store.update_lead_text(lead_id, text.strip())

    def remove_lead(self, lead_id: str) -> None:
        self.store.remove_lead(lead_id)

    def launch(self, check_id: str, models: Sequence[str]) -> list[Thread]:
        """Start one research job per remaining lead and model."""
        if not models:
            raise ValueError("Choose at least one model")
        leads = self.store.list_draft_leads(check_id)
        if not leads:
            raise NothingToLaunchError("There is no lead to research")
        if any(not lead.text.strip() for lead in leads):
            raise ValueError("A lead is empty. Fill it in or remove it.")
        check = self.store.get_check(check_id)
        threads, jobs = self.store.launch_leads(
            check_id,
            models=models,
            search_engine=self._search_engine,
            instructions=check.instructions,
        )
        for job in jobs:
            self.jobs.start(job.id)
        return threads

    def retry_thread(self, thread_id: str) -> list[Job]:
        """Run a failed thread again, once for each model whose latest attempt failed."""
        latest: dict[str, Job] = {}
        for job in self.store.list_jobs(thread_id):
            if job.model not in latest or job.attempt >= latest[job.model].attempt:
                latest[job.model] = job
        failed = [job for job in latest.values() if job.status is JobStatus.FAILED]
        if not failed:
            raise ValueError("This thread has not failed, so there is nothing to try again.")
        again = [
            self.store.create_job(
                thread_id,
                model=job.model,
                search_engine=job.search_engine,
                instructions=job.instructions,
                attempt=job.attempt + 1,
            )
            for job in failed
        ]
        for job in again:
            self.jobs.start(job.id)
        return again

    def thread_status(self, thread_id: str) -> ThreadStatus:
        return summarise(self.store.list_jobs(thread_id))
