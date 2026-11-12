"""The smallest end-to-end path: paste text, get leads, edit them, press Go, watch threads."""

from nicegui import ElementFilter, ui
from nicegui.testing import User

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind, EvidenceItem, Report, Stance
from manyminds.core.services import Services
from support import RecordingModel, until

TEXT = "The bridge opened in 1932."


async def generate_leads(user: User, text: str = TEXT, instructions: str = "") -> None:
    await user.open("/")
    user.find(marker="composer").type(text)
    if instructions:
        user.find(marker="instructions").type(instructions)
    user.find("Generate leads").click()
    await user.should_see("Leads")


async def launch(user: User) -> None:
    await generate_leads(user)
    user.find("Go").click()
    await user.should_see("Threads")


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
    await generate_leads(user, instructions="Prefer archives")

    await user.should_see("Bridge claim")
    await user.should_see(TEXT)
    for lead in ("Lead A", "Lead B", "Lead C"):
        await user.should_see(lead, kind=ui.input)
    await user.should_see("Go")
    assert model.decompose_calls[0]["text"] == TEXT
    assert model.decompose_calls[0]["instructions"] == "Prefer archives"


async def test_generating_with_no_text_asks_for_some(user: User, model: RecordingModel) -> None:
    await user.open("/")

    user.find("Generate leads").click()

    await user.should_see("Paste some text first.")
    assert model.decompose_calls == []


async def test_failed_lead_generation_says_why_and_stays_on_home(
    user: User, model: RecordingModel, services: Services
) -> None:
    model.decompose_error = ModelError(ErrorKind.RATE_LIMIT, "Too many requests")
    await user.open("/")
    user.find(marker="composer").type(TEXT)

    user.find("Generate leads").click()

    await user.should_see("Too many requests")
    await user.should_see(marker="composer")
    assert services.store.list_checks() == []


async def test_there_are_no_checkboxes_in_the_lead_list(user: User) -> None:
    await generate_leads(user)

    with user:
        assert list(ElementFilter(kind=ui.checkbox)) == []


async def test_go_researches_every_lead_left_in_the_list(
    user: User, model: RecordingModel, services: Services
) -> None:
    await generate_leads(user)

    user.find("Go").click()
    await user.should_see("Threads")
    await services.jobs.wait_until_idle()

    assert [call["lead"] for call in model.research_calls] == ["Lead A", "Lead B", "Lead C"]
    assert {call["model"] for call in model.research_calls} == {"vendor/research-model"}


async def test_an_edited_lead_is_researched_as_edited(
    user: User, model: RecordingModel, services: Services
) -> None:
    await generate_leads(user)

    with user.scope(marker="lead-row-1"):
        user.find(kind=ui.input).clear().type("Lead B, reworded")
    user.find("Go").click()
    await user.should_see("Threads")
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
    user.find("Go").click()
    await user.should_see("Threads")
    await services.jobs.wait_until_idle()

    assert [call["lead"] for call in model.research_calls] == ["Lead A", "Lead C"]


async def test_another_model_can_be_chosen(
    user: User, model: RecordingModel, services: Services
) -> None:
    await generate_leads(user)

    user.find(marker="model-picker").click()
    user.find("vendor/other-model").click()
    user.find("Go").click()
    await user.should_see("Threads")
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

    await user.should_not_see("Go")
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
    await user.should_see("Summary")
    await user.should_see("Findings about: Lead A")
    await user.should_see("Supports the lead")
    await user.should_see("A passage relevant to Lead A")
    await user.should_see("Could not be determined")
    await user.should_see("Nothing further was checked.")
    assert model.active == 2


async def test_evidence_links_to_its_source_in_a_new_tab(user: User) -> None:
    await launch(user)
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    user.find(marker="thread-row-0").click()
    await user.should_see("Summary")

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
    await user.should_not_see("Summary")

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
    await user.should_not_see("Summary")


async def test_evidence_is_grouped_by_stance_and_ungrounded_items_are_flagged(
    user: User, model: RecordingModel
) -> None:
    model.reports["Lead A"] = Report(
        summary="Mixed findings.",
        evidence=[
            EvidenceItem(
                url="https://example.org/for",
                quote="It opened in 1932.",
                stance=Stance.SUPPORTS,
                grounded=True,
            ),
            EvidenceItem(
                url="https://example.net/against",
                quote="It opened in 1934.",
                stance=Stance.UNDERMINES,
                grounded=False,
            ),
        ],
        undetermined="Which year is right.",
    )
    await launch(user)
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    user.find(marker="thread-row-0").click()
    await user.should_see("Summary")

    with user.scope(marker="evidence-supports"):
        await user.should_see("It opened in 1932.")
        await user.should_not_see("It opened in 1934.")
        await user.should_not_see("Not found in search results")
    with user.scope(marker="evidence-undermines"):
        await user.should_see("It opened in 1934.")
        await user.should_see("Not found in search results")
        # With no title, the link shows the address itself.
        await user.should_see("https://example.net/against", kind=ui.link)


async def test_a_report_with_no_evidence_says_so(user: User, model: RecordingModel) -> None:
    model.reports["Lead A"] = Report(
        summary="Nothing relevant turned up.", evidence=[], undetermined="Everything."
    )
    await launch(user)
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    user.find(marker="thread-row-0").click()

    await user.should_see("Nothing relevant turned up.")
    await user.should_see("No evidence was found.")
    await user.should_see("Everything.")


async def test_markup_in_model_output_is_shown_as_text_never_rendered(
    user: User, model: RecordingModel
) -> None:
    hostile = '<img src=x onerror="alert(1)"> ![x](https://evil.example/?leak=1)'
    model.reports["Lead A"] = Report(
        summary=hostile,
        evidence=[
            EvidenceItem(
                url="https://example.org/a", title=hostile, quote=hostile, stance=Stance.SUPPORTS
            )
        ],
        undetermined=hostile,
    )
    await launch(user)
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    user.find(marker="thread-row-0").click()
    await user.should_see("Summary")

    with user:
        assert list(ElementFilter(kind=ui.html)) == []
        assert list(ElementFilter(kind=ui.markdown)) == []
        assert list(ElementFilter(kind=ui.image)) == []
        showing = [label.text for label in ElementFilter(kind=ui.label) if hostile in label.text]
    assert len(showing) == 3


async def test_the_thread_page_never_shows_a_verdict(user: User) -> None:
    await launch(user)
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    user.find(marker="thread-row-0").click()
    await user.should_see("Summary")

    for word in ("Verdict", "Confidence", "True", "False", "Rating"):
        await user.should_not_see(word)


async def test_a_check_page_can_be_opened_directly_by_its_address(
    user: User, services: Services
) -> None:
    await launch(user)
    await services.jobs.wait_until_idle()

    await user.open(f"/check/{only_check_id(services)}")

    await user.should_see("Bridge claim")
    await user.should_see("Threads")
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")


async def test_an_unknown_check_says_it_was_not_found(user: User) -> None:
    await user.open("/check/does-not-exist")

    await user.should_see("This check could not be found.")
