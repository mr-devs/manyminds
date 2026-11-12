"""Use cases for a check: generate leads, edit them, launch research."""

import logging
from collections.abc import Awaitable, Sequence

from manyminds.core.errors import ModelError
from manyminds.core.events import ChatUpdated, EventBus
from manyminds.core.jobs import JobManager
from manyminds.core.models import (
    Check,
    ErrorKind,
    Job,
    JobStatus,
    Lead,
    LeadOrigin,
    LeadState,
    Message,
    MessageRole,
    MessageStatus,
    SearchEngine,
    Thread,
    ThreadStatus,
)
from manyminds.core.ports import (
    FAILED,
    FINISHED,
    IN_PROGRESS,
    NOT_STARTED,
    ChatContext,
    LeadNote,
    ModelClient,
    PastTurn,
    Progress,
    ProgressCallback,
)
from manyminds.core.storage import NotFoundError, Store

logger = logging.getLogger(__name__)

INITIAL_LEADS = 5
MAX_LEADS = 25
"""The most leads waiting in one list. Launched leads no longer count."""
TITLE_LENGTH = 60
MAX_TITLE_LENGTH = 120


class NothingToLaunchError(ValueError):
    """There are no draft leads left, for example because another tab launched them."""


class CheckBusyError(ValueError):
    """The check still has research under way."""


class ChatBusyError(ValueError):
    """A reply is still being written."""


class TooManyLeadsError(ValueError):
    """The list of leads waiting to be researched is full."""


def _squash(text: str) -> str:
    return " ".join(text.split())


def _key(text: str) -> str:
    return _squash(text).casefold()


def _unique_leads(leads: Sequence[str], limit: int, existing: Sequence[str] = ()) -> list[str]:
    """Trim, drop blanks, and drop repeats that differ only in case or spacing."""
    seen: set[str] = {_key(text) for text in existing}
    kept: list[str] = []
    for lead in leads:
        text = lead.strip()
        key = _key(text)
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
        bus: EventBus,
        decompose_model: str,
        chat_model: str,
        search_engine: SearchEngine,
    ) -> None:
        self.store = store
        self.jobs = jobs
        self._model = model
        self._bus = bus
        self._decompose_model = decompose_model
        self._chat_model = chat_model
        self._replying: set[str] = set()
        """Checks with a reply being written right now."""
        self._search_engine = search_engine

    def start_check(self, text: str, instructions: str = "") -> Check:
        """Save a check at once and work out its leads in the background.

        The check opens with the user's message and a reply still to come. Each step taken
        is saved under that reply and announced, so the work can be watched.
        """
        reply = self._open(text, instructions)
        self.jobs.spawn(self._settle(reply.check_id, reply, self._opening(reply, instructions)))
        return self.store.get_check(reply.check_id)

    async def create_check(self, text: str, instructions: str = "") -> Check:
        """Generate leads for a pasted text and wait for them. Nothing is kept on failure."""
        reply = self._open(text, instructions)
        try:
            await self._opening(reply, instructions)
        except BaseException:
            self.store.delete_check(reply.check_id)
            raise
        return self.store.get_check(reply.check_id)

    def regenerate(self, check_id: str) -> None:
        """Try again to work out a check's leads, after the first attempt failed."""
        replies = [
            message
            for message in self.store.list_messages(check_id)
            if message.role is MessageRole.ASSISTANT
        ]
        if not replies or replies[0].status is not MessageStatus.FAILED:
            raise ValueError("Lead generation has not failed, so there is nothing to try again.")
        if check_id in self._replying:
            raise ChatBusyError("Wait for the reply before trying again.")
        check = self.store.get_check(check_id)
        reply = self.store.reopen_message(replies[0].id)
        self._bus.publish(ChatUpdated(check_id=check_id))
        self.jobs.spawn(self._settle(check_id, reply, self._opening(reply, check.instructions)))

    def _open(self, text: str, instructions: str) -> Message:
        if not text.strip():
            raise ValueError("The text to check is empty")
        return self.store.open_check(
            title=_squash(text)[:TITLE_LENGTH], source_text=text, instructions=instructions
        )

    async def _opening(self, reply: Message, instructions: str) -> Message:
        """Work out the leads for a check and fill in its opening reply."""
        check = self.store.get_check(reply.check_id)
        decomposition = await self._model.decompose(
            check.source_text,
            instructions,
            count=INITIAL_LEADS,
            avoid=[],
            model=self._decompose_model,
            on_progress=self._recorder(reply),
        )
        leads = _unique_leads(decomposition.leads, INITIAL_LEADS)
        if not leads:
            raise ModelError(ErrorKind.INVALID_OUTPUT, "No leads could be generated for this text.")
        title = _squash(decomposition.title)
        if len(title) > MAX_TITLE_LENGTH:
            title = title[: MAX_TITLE_LENGTH - 1].rstrip() + "…"
        # The title first: if anything fails, no leads are left behind a reply marked failed.
        if title:
            self.store.rename_check(reply.check_id, title)
        return self.store.finish_message(
            reply.id, decomposition.seen.strip(), leads, LeadOrigin.GENERATED
        )

    def _recorder(self, reply: Message) -> ProgressCallback:
        """Saves each step under the reply and tells whoever is watching."""

        def record(progress: Progress) -> None:
            self.store.add_message_step(reply.id, progress.kind, progress.detail)
            self._bus.publish(ChatUpdated(check_id=reply.check_id))

        return record

    def delete_check(self, check_id: str) -> None:
        """Delete a check and its research. Refused while any of that research is running,
        because a running job cannot be stopped and would go on being paid for."""
        if self.store.count_unfinished_jobs(check_id):
            raise CheckBusyError("Research is still running. Wait for it to finish, then delete.")
        if check_id in self._replying:
            raise CheckBusyError("A reply is still being written. Wait for it, then delete.")
        self.store.delete_check(check_id)

    def add_lead(self, check_id: str, message_id: str | None = None) -> Lead:
        """Add an empty lead for the user to fill in, under the given reply or the latest."""
        if len(self.store.list_draft_leads(check_id)) >= MAX_LEADS:
            raise TooManyLeadsError(
                f"A list holds {MAX_LEADS} leads at most. Research these, then add the rest."
            )
        if message_id is None:
            replies = [
                message.id
                for message in self.store.list_messages(check_id)
                if message.role is MessageRole.ASSISTANT
                and message.status is MessageStatus.COMPLETE
            ]
            message_id = replies[-1] if replies else None
        return self.store.add_lead(check_id, "", LeadOrigin.MANUAL, message_id)

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

    def launch_lead(self, lead_id: str, models: Sequence[str]) -> Thread:
        """Start research on one lead, with one job per model. The other leads stay as
        they are."""
        if not models:
            raise ValueError("Choose at least one model")
        try:
            lead = self.store.get_lead(lead_id)
        except NotFoundError:
            raise NothingToLaunchError("This lead is no longer there") from None
        if lead.state is not LeadState.DRAFT:
            raise NothingToLaunchError("This lead has already been started")
        if not lead.text.strip():
            raise ValueError("This lead is empty. Fill it in first.")
        check = self.store.get_check(lead.check_id)
        thread, jobs = self.store.launch_one_lead(
            lead_id,
            models=models,
            search_engine=self._search_engine,
            instructions=check.instructions,
        )
        for job in jobs:
            self.jobs.start(job.id)
        return thread

    async def send(self, check_id: str, text: str) -> Message:
        """Add the user's message to the conversation and return the model's reply.

        Both are saved. A reply that could not be written is saved as failed, with the
        reason. Leads the reply proposes are saved as drafts; nothing is started.
        """
        body = text.strip()
        if not body:
            raise ValueError("Write a message first.")
        self.store.get_check(check_id)
        if check_id in self._replying:
            raise ChatBusyError("Wait for the reply before sending another message.")
        context = self._chat_context(check_id, self.store.list_messages(check_id))
        reply = self.store.begin_turn(check_id, body)
        return await self._settle(check_id, reply, self._reply(reply, body, context))

    async def _settle(self, check_id: str, reply: Message, work: Awaitable[Message]) -> Message:
        """See a reply through: run the work that fills it in, or save why there is none.

        While this runs the check is busy. Watchers are told at the start and at the end,
        whatever happens.
        """
        self._replying.add(check_id)
        try:
            self._bus.publish(ChatUpdated(check_id=check_id))
            try:
                return await work
            except ModelError as error:
                reason = error.message
            except Exception as error:
                # The text of an unexpected error may contain anything, so only its type is
                # kept.
                name = type(error).__name__
                logger.error("A reply on check %s failed unexpectedly: %s", check_id, name)
                reason = f"Unexpected error ({name})"
            try:
                return self.store.fail_message(reply.id, reason)
            except Exception as error:
                logger.error(
                    "A failed reply on check %s could not be recorded: %s",
                    check_id,
                    type(error).__name__,
                )
                return reply
        finally:
            self._replying.discard(check_id)
            self._bus.publish(ChatUpdated(check_id=check_id))

    async def _reply(self, reply: Message, body: str, context: ChatContext) -> Message:
        check_id = reply.check_id
        answer = await self._model.converse(
            body,
            context,
            model=self._chat_model,
            search=self._search_engine,
            on_progress=self._recorder(reply),
        )
        room = MAX_LEADS - len(self.store.list_draft_leads(check_id))
        leads = _unique_leads(
            answer.leads, max(room, 0), [lead.text for lead in self.store.list_leads(check_id)]
        )
        said = answer.body.strip()
        if not said and not leads:
            raise ModelError(ErrorKind.INVALID_OUTPUT, "The model sent back an empty reply.")
        return self.store.finish_message(reply.id, said, leads)

    def _chat_context(self, check_id: str, messages: Sequence[Message]) -> ChatContext:
        turns = tuple(
            PastTurn(message.role, message.body)
            for message in messages
            if message.status is MessageStatus.COMPLETE and message.body
        )
        threads = {thread.lead_id: thread for thread in self.store.list_threads(check_id)}
        notes = []
        for lead in self.store.list_leads(check_id):
            thread = threads.get(lead.id)
            if thread is None:
                if lead.text.strip():
                    notes.append(LeadNote(lead.text, NOT_STARTED))
                continue
            jobs = self.store.list_jobs(thread.id)
            status = summarise(jobs)
            if status is ThreadStatus.FINISHED:
                reports = tuple(
                    report for job in jobs if (report := self.store.get_report(job.id)) is not None
                )
                notes.append(LeadNote(thread.lead_text, FINISHED, reports))
            elif status is ThreadStatus.FAILED:
                notes.append(LeadNote(thread.lead_text, FAILED))
            else:
                notes.append(LeadNote(thread.lead_text, IN_PROGRESS))
        return ChatContext(turns=turns, leads=tuple(notes))

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
