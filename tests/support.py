"""Shared test doubles and helpers."""

import asyncio
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from nicegui import ElementFilter
from nicegui.testing import User

from manyminds.core.models import (
    EvidenceItem,
    JobEventKind,
    Report,
    SearchEngine,
    Stance,
    Usage,
)
from manyminds.core.ports import (
    ChatContext,
    ChatReply,
    Decomposition,
    Progress,
    ProgressCallback,
    ResearchResult,
)


async def until(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    """Let other tasks run until the condition holds; fail if it never does."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        if loop.time() > deadline:
            raise AssertionError("condition was not met in time")
        await asyncio.sleep(0)


def start_all(user: User) -> None:
    """Start research on every waiting lead: "Research all", or Go when there is only one."""
    with user:
        several = list(ElementFilter(marker="research-all"))
    user.find(marker="research-all" if several else "go").click()


def report_for(lead: str) -> Report:
    return Report(
        summary=f"Findings about: {lead}",
        evidence=[
            EvidenceItem(
                url="https://example.org/source",
                title="Source",
                quote=f"A passage relevant to {lead}",
                stance=Stance.SUPPORTS,
                grounded=True,
            )
        ],
        undetermined="Nothing further was checked.",
    )


@dataclass
class RecordingModel:
    """A model client that records calls and lets a test decide when research finishes."""

    title: str = "A title"
    leads: Sequence[str] = ("First lead", "Second lead")
    seen: str = ""
    """What lead generation reports having read from links and images."""
    decompose_error: Exception | None = None
    hold_decompose: bool = False
    """When true, lead generation waits until the test calls release_decompose()."""
    steps: Sequence[Progress] = ()
    """Progress reported while leads are generated or a reply is written."""
    failures: dict[str, Exception] = field(default_factory=dict)
    reports: dict[str, Report] = field(default_factory=dict)
    usages: dict[str, Usage] = field(default_factory=dict)
    """What particular leads consumed; other leads report no usage."""
    late_progress: dict[str, list[Progress]] = field(default_factory=dict)
    """Progress to report for a lead once it is released, before it finishes."""
    """Reports to return for particular leads, in place of the default one."""
    hold: bool = False
    """When true, each research call waits until the test calls release()."""

    reply: str = "A reply"
    """What the chat model says back."""
    proposed: Sequence[str] = ()
    """Leads the chat model proposes with its reply."""
    converse_error: Exception | None = None
    hold_reply: bool = False
    """When true, the chat reply waits until the test calls release_reply()."""

    decompose_calls: list[dict[str, Any]] = field(default_factory=list)
    converse_calls: list[dict[str, Any]] = field(default_factory=list)
    converse_searches: list[SearchEngine] = field(default_factory=list)
    _reply_gate: asyncio.Event = field(default_factory=asyncio.Event)
    _decompose_gate: asyncio.Event = field(default_factory=asyncio.Event)
    research_calls: list[dict[str, Any]] = field(default_factory=list)
    active: int = 0
    max_active: int = 0
    _gates: dict[str, asyncio.Event] = field(default_factory=dict)

    def _gate(self, lead: str) -> asyncio.Event:
        return self._gates.setdefault(lead, asyncio.Event())

    def release(self, lead: str) -> None:
        self._gate(lead).set()

    def release_reply(self) -> None:
        self._reply_gate.set()

    def release_decompose(self) -> None:
        self._decompose_gate.set()

    def release_all(self) -> None:
        self.hold = False
        self.hold_reply = False
        self.hold_decompose = False
        self._reply_gate.set()
        self._decompose_gate.set()
        for gate in self._gates.values():
            gate.set()

    async def decompose(
        self,
        text: str,
        instructions: str,
        *,
        count: int,
        avoid: Sequence[str],
        model: str,
        on_progress: ProgressCallback | None = None,
    ) -> Decomposition:
        self.decompose_calls.append(
            {
                "text": text,
                "instructions": instructions,
                "count": count,
                "avoid": list(avoid),
                "model": model,
            }
        )
        for step in self.steps:
            if on_progress is not None:
                on_progress(step)
        if self.hold_decompose:
            await self._decompose_gate.wait()
        if self.decompose_error is not None:
            raise self.decompose_error
        return Decomposition(title=self.title, leads=list(self.leads), seen=self.seen)

    async def converse(
        self,
        message: str,
        context: ChatContext,
        *,
        model: str,
        search: SearchEngine = SearchEngine.EXA,
        on_progress: ProgressCallback | None = None,
    ) -> ChatReply:
        self.converse_calls.append({"message": message, "context": context, "model": model})
        self.converse_searches.append(search)
        for step in self.steps:
            if on_progress is not None:
                on_progress(step)
        if self.hold_reply:
            await self._reply_gate.wait()
        if self.converse_error is not None:
            raise self.converse_error
        return ChatReply(body=self.reply, leads=list(self.proposed))

    async def research(
        self,
        lead: str,
        source_text: str,
        instructions: str,
        *,
        model: str,
        search: SearchEngine,
        on_progress: ProgressCallback,
    ) -> ResearchResult:
        self.research_calls.append(
            {
                "lead": lead,
                "source_text": source_text,
                "instructions": instructions,
                "model": model,
                "search": search,
            }
        )
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            on_progress(Progress(JobEventKind.SEARCHING, f"query for {lead}"))
            if self.hold:
                await self._gate(lead).wait()
            await asyncio.sleep(0)
            for progress in self.late_progress.get(lead, []):
                on_progress(progress)
            if lead in self.failures:
                raise self.failures[lead]
            return ResearchResult(
                report=self.reports.get(lead) or report_for(lead),
                usage=self.usages.get(lead, Usage()),
            )
        finally:
            self.active -= 1


@dataclass
class _Fault:
    sql_part: str
    param: object
    times: int | None
    skip: int


class Faults:
    """Database failures for a test to inject, matched against the SQL being run."""

    def __init__(self) -> None:
        self._rules: list[_Fault] = []

    def fail(
        self, sql_part: str, *, param: object = None, times: int | None = 1, skip: int = 0
    ) -> None:
        """Fail statements containing sql_part (and, if given, having param among their values).

        The first `skip` matches succeed; the next `times` fail (None means every one).
        """
        self._rules.append(_Fault(sql_part, param, times, skip))

    def check(self, sql: str, parameters: Sequence[Any]) -> None:
        for rule in self._rules:
            if rule.sql_part not in sql:
                continue
            if rule.param is not None and rule.param not in list(parameters):
                continue
            if rule.skip > 0:
                rule.skip -= 1
                continue
            if rule.times is None:
                raise sqlite3.OperationalError("injected fault")
            if rule.times > 0:
                rule.times -= 1
                raise sqlite3.OperationalError("injected fault")


def flaky_connection(faults: Faults) -> type[sqlite3.Connection]:
    """A real SQLite connection class that fails when the given faults say so."""

    class FlakyConnection(sqlite3.Connection):
        def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
            faults.check(sql, parameters)
            return super().execute(sql, parameters)

    return FlakyConnection
