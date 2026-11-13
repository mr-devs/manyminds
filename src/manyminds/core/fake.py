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
from manyminds.core.ports import (
    FINISHED,
    ChatContext,
    ChatReply,
    Decomposition,
    Progress,
    ProgressCallback,
    ResearchResult,
)

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

THINKING = """\
Demo thinking. A real model's reasoning would appear here as it works.
The lead to look into is: {lead}
A sensible first step is to find who said it first and where.
After that, look for records made at the time that could confirm or contradict it.
If the first search is thin, try again with different wording."""

SOURCES = """\
Demo source A: https://example.org/demo/{slug}/a
  A placeholder passage standing in for what a search result would say.
Demo source B: https://example.org/demo/{slug}/b
  A second placeholder passage, this one pointing the other way."""

NOTES = """\
## Demo notes

Here a real model would write up what it found. **Nothing below is real.**

### Useful sources

1. **Demo source A:** https://example.org/demo/a
   **Passage:** "A placeholder passage that supports the lead."
   **Relation to lead:** Supports it.
2. **Demo source B:** [a second placeholder](https://example.org/demo/b)
   **Relation to lead:** Cuts against it.

- Neither settles the matter.
- What remains unknown is listed as `could not be determined`."""
TITLE_LENGTH = 40

Sleep = Callable[[float], Awaitable[None]]


def _title(text: str) -> str:
    # What the user wrote, without the notes on attached images that follow it.
    squashed = " ".join(text.split("[Attached image")[0].split()) or "an image"
    if len(squashed) > TITLE_LENGTH:
        squashed = squashed[:TITLE_LENGTH].rsplit(" ", 1)[0] + "…"
    return f"Demo: {squashed}"


def _slug(lead: str) -> str:
    return f"{zlib.crc32(lead.encode()):08x}"


class FakeModelClient:
    def __init__(self, *, sleep: Sleep = asyncio.sleep) -> None:
        self._sleep = sleep

    async def decompose(
        self,
        text: str,
        instructions: str,
        *,
        count: int,
        avoid: Sequence[str],
        model: str,
        images: Sequence[str | None] = (),
        on_progress: ProgressCallback | None = None,
    ) -> Decomposition:
        if on_progress is not None:
            on_progress(Progress(JobEventKind.NOTE, "Demo: reading what you shared"))
            await self._sleep(0.7)
            on_progress(Progress(JobEventKind.NOTE, "Writing the leads"))
            await self._sleep(0.7)
        fresh = [lead for lead in LEADS if lead not in set(avoid)]
        return Decomposition(title=_title(text), leads=fresh[:count])

    async def describe_image(self, media_type: str, data: bytes, *, model: str) -> str:
        await self._sleep(0.6)
        return "Demo description. A real model would say here what the attached image shows."

    async def converse(
        self,
        message: str,
        context: ChatContext,
        *,
        model: str,
        search: SearchEngine = SearchEngine.EXA,
        images: Sequence[str | None] = (),
        on_progress: ProgressCallback | None = None,
    ) -> ChatReply:
        await self._sleep(0.8)
        finished = [note for note in context.leads if note.state == FINISHED]
        lines = [
            "Demo reply. A real model would answer your message here, drawing on the "
            "finished research.",
            f"{len(finished)} of {len(context.leads)} leads have a finished report.",
        ]
        lines += [f"- {note.text}: {note.reports[0].summary}" for note in finished if note.reports]
        known = {note.text for note in context.leads}
        wants_leads = "lead" in message.casefold()
        fresh = [lead for lead in LEADS if lead not in known][:3] if wants_leads else []
        return ChatReply(body="\n".join(lines), leads=fresh)

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
        slug = _slug(lead)
        on_progress(Progress(JobEventKind.THINKING, THINKING.format(lead=lead)))
        on_progress(Progress(JobEventKind.SEARCHING, lead))
        await self._sleep(step)
        on_progress(Progress(JobEventKind.SOURCES_FOUND, SOURCES.format(slug=slug)))
        await self._sleep(step)
        if lead == FAILING_LEAD:
            raise ModelError(ErrorKind.PROVIDER, "Demo failure: this lead is scripted to fail.")
        on_progress(Progress(JobEventKind.MESSAGE, NOTES))
        on_progress(Progress(JobEventKind.WRITING))
        await self._sleep(step / 2)
        report = Report(
            summary=f"Demo report for the lead “{lead}”. No real search was run.",
            evidence=[
                EvidenceItem(
                    url=f"https://example.org/demo/{slug}/a",
                    title="Demo source A",
                    quote="A placeholder passage standing in for a quotation supporting the lead.",
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
