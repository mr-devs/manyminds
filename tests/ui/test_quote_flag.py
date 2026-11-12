"""Evidence whose quote was not found in the returned excerpt is visibly flagged."""

from __future__ import annotations

from nicegui.testing import User

from manyminds.core.models import EvidenceItem, Report, Stance
from support import RecordingModel


def evidence(quote: str, matched: bool | None) -> EvidenceItem:
    return EvidenceItem(
        url="https://example.org/source",
        title="Source",
        quote=quote,
        stance=Stance.SUPPORTS,
        grounded=True,
        quote_matched=matched,
    )


async def test_only_the_unmatched_quote_is_flagged(user: User, model: RecordingModel) -> None:
    model.reports["Lead A"] = Report(
        summary="Three passages.",
        evidence=[
            evidence("A passage the search returned.", True),
            evidence("A passage nobody can find.", False),
            evidence("A passage with no excerpt to check.", None),
        ],
        undetermined="Nothing else.",
    )
    await user.open("/")
    user.find(marker="composer").type("The bridge opened in 1932.")
    user.find("Generate leads").click()
    await user.should_see("Leads to research")
    user.find("Go").click()
    await user.should_see("Threads")
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    user.find(marker="thread-row-0").click()

    await user.should_see("A passage nobody can find.")
    flags = user.find("Quote not found in the search result")
    assert len(flags.elements) == 1
    await user.should_not_see("Not found in search results")
