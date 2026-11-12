"""Use cases for a check: generate leads, edit them, launch research."""

from collections.abc import Sequence

from manyminds.core.errors import ModelError
from manyminds.core.jobs import JobManager
from manyminds.core.models import (
    Check,
    ErrorKind,
    Job,
    JobStatus,
    SearchEngine,
    Thread,
    ThreadStatus,
)
from manyminds.core.ports import ModelClient
from manyminds.core.storage import Store

INITIAL_LEADS = 10
TITLE_LENGTH = 60


class NothingToLaunchError(ValueError):
    """There are no draft leads left, for example because another tab launched them."""


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

    def thread_status(self, thread_id: str) -> ThreadStatus:
        return summarise(self.store.list_jobs(thread_id))
