"""Shared test doubles and helpers."""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from manyminds.core.models import EvidenceItem, JobEventKind, Report, SearchEngine, Stance
from manyminds.core.ports import Decomposition, Progress, ProgressCallback, ResearchResult


async def until(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    """Let other tasks run until the condition holds; fail if it never does."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        if loop.time() > deadline:
            raise AssertionError("condition was not met in time")
        await asyncio.sleep(0)


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
    decompose_error: Exception | None = None
    failures: dict[str, Exception] = field(default_factory=dict)
    hold: bool = False
    """When true, each research call waits until the test calls release()."""

    decompose_calls: list[dict[str, Any]] = field(default_factory=list)
    research_calls: list[dict[str, Any]] = field(default_factory=list)
    active: int = 0
    max_active: int = 0
    _gates: dict[str, asyncio.Event] = field(default_factory=dict)

    def _gate(self, lead: str) -> asyncio.Event:
        return self._gates.setdefault(lead, asyncio.Event())

    def release(self, lead: str) -> None:
        self._gate(lead).set()

    def release_all(self) -> None:
        self.hold = False
        for gate in self._gates.values():
            gate.set()

    async def decompose(
        self, text: str, instructions: str, *, count: int, avoid: Sequence[str], model: str
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
        if self.decompose_error is not None:
            raise self.decompose_error
        return Decomposition(title=self.title, leads=list(self.leads))

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
            if lead in self.failures:
                raise self.failures[lead]
            return ResearchResult(report=report_for(lead))
        finally:
            self.active -= 1
