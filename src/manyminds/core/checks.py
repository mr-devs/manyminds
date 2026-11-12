"""Use cases for a check: generate leads, edit them, launch research."""

from collections.abc import Sequence

from manyminds.core.errors import ModelError
from manyminds.core.jobs import JobManager
from manyminds.core.models import (
    Check,
    ErrorKind,
    Job,
    JobStatus,
    LeadOrigin,
    SearchEngine,
    Thread,
    ThreadStatus,
)
from manyminds.core.ports import ModelClient
from manyminds.core.storage import Store

INITIAL_LEADS = 10
TITLE_LENGTH = 60


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
        check = self.store.create_check(title=title, source_text=text, instructions=instructions)
        for lead in leads:
            self.store.add_lead(check.id, lead, LeadOrigin.GENERATED)
        return check

    def update_lead(self, lead_id: str, text: str) -> None:
        if not text.strip():
            raise ValueError("A lead cannot be empty")
        self.store.update_lead_text(lead_id, text.strip())

    def remove_lead(self, lead_id: str) -> None:
        self.store.remove_lead(lead_id)

    def launch(self, check_id: str, models: Sequence[str]) -> list[Thread]:
        """Start one research job per remaining lead and model."""
        if not models:
            raise ValueError("Choose at least one model")
        leads = self.store.list_draft_leads(check_id)
        if not leads:
            raise ValueError("There is no lead to research")
        check = self.store.get_check(check_id)
        threads = []
        for lead in leads:
            thread = self.store.launch_lead(lead.id)
            threads.append(thread)
            for model in models:
                job = self.store.create_job(
                    thread.id,
                    model=model,
                    search_engine=self._search_engine,
                    instructions=check.instructions,
                )
                self.jobs.start(job.id)
        return threads

    def thread_status(self, thread_id: str) -> ThreadStatus:
        return summarise(self.store.list_jobs(thread_id))
