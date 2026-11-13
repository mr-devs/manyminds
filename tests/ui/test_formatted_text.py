"""Markdown from a model is formatted with plain text elements, never handed to the browser."""

from nicegui import ElementFilter, ui
from nicegui.testing import User

from manyminds.core.models import JobEventKind
from manyminds.core.ports import Progress
from manyminds.core.services import Services
from support import RecordingModel, start_all

NOTES = (
    "## Research notes\n\n"
    "- **The post** names `@someone`.\n"
    "- See [the archive](https://archive.example/a).\n\n"
    '<img src=x onerror="alert(1)"> [bad](javascript:alert(1))'
)


async def open_thread_with(user: User, model: RecordingModel, kind: JobEventKind) -> None:
    model.leads = ["Lead A"]
    model.late_progress["Lead A"] = [Progress(kind, NOTES)]
    await user.open("/")
    user.find(marker="composer").type("A claim.")
    user.find("Generate leads").click()
    await user.should_see(marker="lead-list")
    start_all(user)
    await user.should_see(marker="thread-row-0")
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    user.find(marker="thread-row-0").click()
    await user.should_see("Report ready")


def classes_of(user: User, text: str) -> set[str]:
    with user:
        (label,) = [label for label in ElementFilter(kind=ui.label) if label.text == text]
    return set(label.classes)


async def test_an_agents_notes_are_formatted(user: User, model: RecordingModel) -> None:
    await open_thread_with(user, model, JobEventKind.MESSAGE)

    assert "mm-md-h2" in classes_of(user, "Research notes")
    assert "mm-md-bold" in classes_of(user, "The post")
    assert "mm-md-code" in classes_of(user, "@someone")
    await user.should_not_see("## Research notes")
    await user.should_not_see("**The post**")
    with user:
        links = {link.text: link.props["href"] for link in ElementFilter(kind=ui.link)}
    assert links["the archive"] == "https://archive.example/a"


async def test_thinking_is_formatted_too(user: User, model: RecordingModel) -> None:
    await open_thread_with(user, model, JobEventKind.THINKING)

    assert "mm-md-bold" in classes_of(user, "The post")


async def test_formatting_never_hands_markup_to_the_browser(
    user: User, model: RecordingModel
) -> None:
    await open_thread_with(user, model, JobEventKind.MESSAGE)

    await user.should_see(
        kind=ui.label, content='<img src=x onerror="alert(1)"> [bad](javascript:alert(1))'
    )
    with user:
        assert list(ElementFilter(kind=ui.html)) == []
        assert list(ElementFilter(kind=ui.markdown)) == []
        assert list(ElementFilter(kind=ui.image)) == []
        hrefs = [link.props["href"] for link in ElementFilter(kind=ui.link)]
    assert all(href.startswith(("https://", "http://", "/")) for href in hrefs)


async def test_a_reply_in_the_conversation_is_formatted(
    user: User, model: RecordingModel, services: Services
) -> None:
    model.reply = "**Two** threads agree.\n\n1. The year is 1932."
    await user.open("/")
    user.find(marker="composer").type("A claim.")
    user.find("Generate leads").click()
    await user.should_see(marker="lead-list")

    user.find(marker="composer").type("Summarise.")
    user.find("Send").click()

    await user.should_see(marker="reply", content="threads agree.")
    assert "mm-md-bold" in classes_of(user, "Two")
    await user.should_see("The year is 1932.")
    await user.should_not_see("**Two**")
