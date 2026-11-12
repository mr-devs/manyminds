"""A scripted stand-in for a real model: offline, free, deterministic.

Used by demo mode so the whole app can be tried without a key. Everything it produces is
labelled as demo content and points at example.org.
"""

import asyncio
import zlib
from collections.abc import Awaitable, Callable, Sequence

from manyminds.core.errors import ModelError
from manyminds.core.models import (
    ErrorKind,
    EvidenceItem,
    JobEventKind,
    Report,
    SearchEngine,
    Stance,
)
from manyminds.core.ports import Decomposition, Progress, ProgressCallback, ResearchResult

LEADS: Sequence[str] = (
    "Who first made this claim, and in what context?",
    "What primary source, if any, is the claim based on?",
    "Do the dates and figures in the text match official records?",
    "Has any named person or organisation in the text confirmed or denied it?",
    "What do independent experts say about the central assertion?",
    "Is there earlier reporting that contradicts the text?",
    "Are the quoted statistics presented with their original caveats?",
    "Has the claim changed as it has been repeated?",
    "Is there relevant context the text leaves out?",
    "Have similar claims been made before, and how did they hold up?",
    "Are the images or documents referred to authentic?",
    "Who benefits if the claim is widely believed?",
    "Do other languages' sources report the same facts?",
    "What would have to be true for the claim to hold?",
    "Is the cited study peer reviewed and has it been replicated?",
    "Does the timeline in the text hold together?",
    "Are the people quoted in a position to know?",
    "What do the original data show when examined directly?",
    "Has the source issued any correction or retraction?",
    "Are there official statements that address this directly?",
)
FAILING_LEAD = LEADS[3]
TITLE_LENGTH = 40

Sleep = Callable[[float], Awaitable[None]]


def _title(text: str) -> str:
    squashed = " ".join(text.split())
    if len(squashed) > TITLE_LENGTH:
        squashed = squashed[:TITLE_LENGTH].rsplit(" ", 1)[0] + "…"
    return f"Demo: {squashed}"


def _slug(lead: str) -> str:
    return f"{zlib.crc32(lead.encode()):08x}"


class FakeModelClient:
    def __init__(self, *, sleep: Sleep = asyncio.sleep) -> None:
        self._sleep = sleep

    async def decompose(
        self, text: str, instructions: str, *, count: int, avoid: Sequence[str], model: str
    ) -> Decomposition:
        fresh = [lead for lead in LEADS if lead not in set(avoid)]
        return Decomposition(title=_title(text), leads=fresh[:count])

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
        # Each lead takes its own, repeatable amount of time so threads finish out of order.
        step = 0.4 + (zlib.crc32(lead.encode()) % 20) / 10
        on_progress(Progress(JobEventKind.SEARCHING, lead))
        await self._sleep(step)
        on_progress(Progress(JobEventKind.SOURCES_FOUND, "2 sources"))
        await self._sleep(step)
        if lead == FAILING_LEAD:
            raise ModelError(ErrorKind.PROVIDER, "Demo failure: this lead is scripted to fail.")
        on_progress(Progress(JobEventKind.WRITING))
        await self._sleep(step / 2)
        slug = _slug(lead)
        report = Report(
            summary=f"Demo report for the lead “{lead}”. No real search was run.",
            evidence=[
                EvidenceItem(
                    url=f"https://example.org/demo/{slug}/a",
                    title="Demo source A",
                    quote="A placeholder passage standing in for a quotation that supports the lead.",
                    stance=Stance.SUPPORTS,
                    grounded=True,
                ),
                EvidenceItem(
                    url=f"https://example.org/demo/{slug}/b",
                    title="Demo source B",
                    quote="A placeholder passage standing in for a quotation that cuts against it.",
                    stance=Stance.UNDERMINES,
                    grounded=True,
                ),
            ],
            undetermined="Everything: this is demo content, so nothing was actually checked.",
        )
        return ResearchResult(report=report)
