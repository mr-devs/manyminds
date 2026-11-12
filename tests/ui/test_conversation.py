"""The check page as a running conversation, with leads started one at a time."""

import asyncio

from nicegui import ElementFilter, ui
from nicegui.testing import User

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind
from manyminds.core.services import Services
from support import RecordingModel, until

TEXT = "The bridge opened in 1932."


async def new_check(user: User) -> None:
    await user.open("/")
    user.find(marker="composer").type(TEXT)
    user.find("Generate leads").click()
    await user.should_see(marker="lead-list")


def only_check_id(services: Services) -> str:
    (check,) = services.store.list_checks()
    return check.id


def lead_boxes(user: User) -> list[str]:
    with user:
        return [box.value for box in ElementFilter(kind=ui.textarea).within(marker="lead-list")]


async def say(user: User, text: str) -> None:
    user.find(marker="composer").type(text)
    user.find("Send").click()


# -- the opening exchange ------------------------------------------------------------------


async def test_the_pasted_text_is_shown_as_the_users_message_with_the_leads_beneath(
    user: User,
) -> None:
    await new_check(user)

    await user.should_see(marker="user-message", content=TEXT)
    await user.should_see("Leads worth researching. Start any of them, reword them, or leave them.")
    assert lead_boxes(user) == ["Lead A", "Lead B", "Lead C"]
    await user.should_see(marker="composer")
    await user.should_see("Send")


# -- starting leads one at a time ----------------------------------------------------------


async def test_go_starts_that_lead_alone_and_its_row_becomes_the_way_into_its_thread(
    user: User, model: RecordingModel, services: Services
) -> None:
    await new_check(user)

    with user.scope(marker="lead-row-1"):
        user.find(marker="go").click()
    await user.should_see(marker="thread-row-0")
    await services.jobs.wait_until_idle()

    assert [call["lead"] for call in model.research_calls] == ["Lead B"]
    with user.scope(marker="thread-row-0"):
        await user.should_see("Lead B")
        await user.should_see("Finished")
    assert lead_boxes(user) == ["Lead A", "Lead C"]
    await user.should_not_see(marker="thread-row-1")


async def test_a_started_lead_stays_in_its_place_in_the_list(user: User) -> None:
    await new_check(user)

    with user.scope(marker="lead-row-1"):
        user.find(marker="go").click()
    await user.should_see(marker="thread-row-0")

    with user:
        (rows,) = list(ElementFilter(marker="lead-list"))
        order = [next(iter(child._markers)) for child in rows.default_slot.children]
    assert order == ["lead-row-0", "thread-row-0", "lead-row-1"]


async def test_a_started_row_opens_its_thread(user: User, services: Services) -> None:
    await new_check(user)
    with user.scope(marker="lead-row-0"):
        user.find(marker="go").click()
    await user.should_see(marker="thread-row-0")
    await services.jobs.wait_until_idle()

    user.find(marker="thread-row-0").click()

    await user.should_see("Report")
    await user.should_see("Findings about: Lead A")


async def test_research_all_starts_every_lead_that_has_text(
    user: User, model: RecordingModel, services: Services
) -> None:
    await new_check(user)
    with user.scope(marker="lead-row-1"):
        user.find(kind=ui.input).clear()

    user.find(marker="research-all").click()
    await user.should_see(marker="thread-row-1")
    await services.jobs.wait_until_idle()

    assert [call["lead"] for call in model.research_calls] == ["Lead A", "Lead C"]
    assert lead_boxes(user) == [""]


async def test_go_uses_the_model_chosen_beside_the_message_box(
    user: User, model: RecordingModel, services: Services
) -> None:
    await new_check(user)
    user.find(marker="model-picker").click()
    user.find("vendor/other-model").click()

    with user.scope(marker="lead-row-0"):
        user.find(marker="go").click()
    await user.should_see(marker="thread-row-0")
    await services.jobs.wait_until_idle()

    assert [call["model"] for call in model.research_calls] == ["vendor/other-model"]


# -- the conversation continues ------------------------------------------------------------


async def test_a_message_and_its_reply_appear_below_and_the_box_is_emptied(
    user: User, model: RecordingModel
) -> None:
    model.reply = "Two threads agree on the year."
    await new_check(user)

    await say(user, "Summarise the findings.")

    await user.should_see(marker="reply", content="Two threads agree on the year.")
    with user:
        said = [label.text for label in ElementFilter(kind=ui.label, marker="user-message")]
        (box,) = list(ElementFilter(kind=ui.textarea, marker="composer"))
    assert said == [TEXT, "Summarise the findings."]
    assert box.value == ""
    assert model.converse_calls[0]["message"] == "Summarise the findings."


async def test_a_reply_being_written_says_so_until_it_lands(
    user: User, model: RecordingModel
) -> None:
    model.hold_reply = True
    model.reply = "Here it is."
    await new_check(user)

    await say(user, "Summarise.")
    await user.should_see("Writing a reply")
    await user.should_see(marker="user-message", content="Summarise.")

    model.release_reply()
    await user.should_see("Here it is.")
    await user.should_not_see("Writing a reply")


async def test_leads_proposed_in_a_reply_get_their_own_rows_and_start_nothing(
    user: User, model: RecordingModel, services: Services
) -> None:
    model.reply = "Two more things could be looked into."
    model.proposed = ["Who built the bridge?", "Who paid for it?"]
    await new_check(user)

    await say(user, "What else?")
    await user.should_see(marker="lead-row-4")

    assert lead_boxes(user) == [
        "Lead A",
        "Lead B",
        "Lead C",
        "Who built the bridge?",
        "Who paid for it?",
    ]
    assert model.research_calls == []
    assert services.store.list_threads(only_check_id(services)) == []

    with user.scope(marker="lead-row-3"):
        user.find(marker="go").click()
    await user.should_see(marker="thread-row-0")
    await services.jobs.wait_until_idle()
    assert [call["lead"] for call in model.research_calls] == ["Who built the bridge?"]


async def test_a_reply_that_fails_says_why_in_its_place(user: User, model: RecordingModel) -> None:
    model.converse_error = ModelError(ErrorKind.CREDITS, "Your OpenRouter credit has run out.")
    await new_check(user)

    await say(user, "Summarise.")

    await user.should_see(
        marker="reply-error", content="No reply: Your OpenRouter credit has run out."
    )
    await user.should_see(marker="user-message", content="Summarise.")


async def test_an_empty_message_is_not_sent(user: User, model: RecordingModel) -> None:
    await new_check(user)

    user.find("Send").click()

    await user.should_see("Write a message first.")
    assert model.converse_calls == []


async def test_a_second_message_while_a_reply_is_awaited_is_kept_in_the_box(
    user: User, model: RecordingModel
) -> None:
    model.hold_reply = True
    await new_check(user)
    await say(user, "First.")
    await user.should_see("Writing a reply")

    await say(user, "Second.")

    await user.should_see("Wait for the reply before sending another message.")
    with user:
        (box,) = list(ElementFilter(kind=ui.textarea, marker="composer"))
    assert box.value == "Second."
    assert len(model.converse_calls) == 1


async def test_enter_sends_the_message(user: User, model: RecordingModel) -> None:
    """The key itself is handled in the browser; this checks that it is wired to sending."""
    await new_check(user)
    user.find(marker="composer").type("Summarise.")

    user.find(marker="composer").trigger("keydown.enter.exact.prevent")

    await user.should_see(marker="reply", content="A reply")
    assert [call["message"] for call in model.converse_calls] == ["Summarise."]


async def test_enter_generates_leads_on_the_home_page(user: User, services: Services) -> None:
    await user.open("/")
    user.find(marker="composer").type(TEXT)

    user.find(marker="composer").trigger("keydown.enter.exact.prevent")

    await user.should_see(marker="lead-list")
    assert len(services.store.list_checks()) == 1


async def test_a_message_sent_from_elsewhere_appears_on_an_open_page(
    user: User, model: RecordingModel, services: Services
) -> None:
    model.reply = "Sent from another tab."
    await new_check(user)

    task = asyncio.create_task(services.checks.send(only_check_id(services), "From elsewhere."))
    await task

    await user.should_see(marker="user-message", content="From elsewhere.")
    await user.should_see(marker="reply", content="Sent from another tab.")


async def test_the_whole_conversation_is_there_when_the_check_is_opened_again(
    user: User, model: RecordingModel, services: Services
) -> None:
    model.reply = "An answer worth keeping."
    await new_check(user)
    await say(user, "Summarise.")
    await user.should_see("An answer worth keeping.")

    await user.open("/")
    await user.open(f"/check/{only_check_id(services)}")

    await user.should_see(marker="user-message", content=TEXT)
    await user.should_see(marker="user-message", content="Summarise.")
    await user.should_see(marker="reply", content="An answer worth keeping.")
    assert lead_boxes(user) == ["Lead A", "Lead B", "Lead C"]


async def test_a_reply_with_markup_is_shown_as_plain_text(
    user: User, model: RecordingModel
) -> None:
    model.reply = "<script>alert(1)</script> **bold** [x](javascript:alert(1))"
    model.proposed = ["<img src=x onerror=alert(1)> lead"]
    await new_check(user)

    await say(user, "Summarise.")

    await user.should_see(kind=ui.label, content=model.reply)
    await user.should_see(kind=ui.textarea, content="<img src=x onerror=alert(1)> lead")
    with user:
        assert list(ElementFilter(kind=ui.html)) == []
        assert list(ElementFilter(kind=ui.markdown)) == []


async def test_research_status_changes_in_place_while_the_user_is_mid_conversation(
    user: User, model: RecordingModel
) -> None:
    model.hold = True
    await new_check(user)
    with user.scope(marker="lead-row-0"):
        user.find(marker="go").click()
    await until(lambda: model.active == 1)
    with user.scope(marker="thread-row-0"):
        await user.should_see("Working")
    await say(user, "How is it going?")
    await user.should_see(marker="reply", content="A reply")

    model.release("Lead A")

    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")


async def test_what_was_read_from_links_is_shown_above_the_leads_as_plain_text(
    user: User, model: RecordingModel
) -> None:
    model.seen = (
        "Opened: <b>A post</b> (https://mirror.example/p)\nImage https://i.example/a.jpg: A stage."
    )
    await new_check(user)

    await user.should_see("What was read from your links")
    await user.should_see(kind=ui.label, content="Opened: <b>A post</b> (https://mirror.example/p)")
    await user.should_see("Leads worth researching. Start any of them, reword them, or leave them.")
    assert lead_boxes(user) == ["Lead A", "Lead B", "Lead C"]
