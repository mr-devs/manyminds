"""Interface behaviours pinned down after independent reviews of milestone 1a."""

from nicegui import ElementFilter, ui
from nicegui.testing import User

from manyminds.core.models import Report
from manyminds.core.services import Services
from support import Faults, RecordingModel, start_all

TEXT = "The bridge opened in 1932."
OUT_OF_DATE = "This list was out of date and has been refreshed."


async def generate_leads(user: User) -> None:
    await user.open("/")
    user.find(marker="composer").type(TEXT)
    user.find("Generate leads").click()
    await user.should_see(marker="lead-list")


def lead_boxes(user: User) -> list[str]:
    with user:
        return [box.value for box in ElementFilter(kind=ui.textarea).within(marker="lead-list")]


# -- empty leads -----------------------------------------------------------------------------


async def test_go_is_refused_on_an_empty_lead(
    user: User, model: RecordingModel, services: Services
) -> None:
    await generate_leads(user)

    with user.scope(marker="lead-row-1"):
        user.find(kind=ui.input).clear()
        user.find(marker="go").click()

    await user.should_see("This lead is empty. Fill it in first.")
    await user.should_not_see(marker="thread-row-0")
    assert model.research_calls == []
    (check,) = services.store.list_checks()
    assert services.store.list_threads(check.id) == []


async def test_an_emptied_lead_can_be_refilled_and_launched(
    user: User, model: RecordingModel, services: Services
) -> None:
    await generate_leads(user)

    with user.scope(marker="lead-row-1"):
        user.find(kind=ui.input).clear()
        user.find(kind=ui.input).type("Lead B, rewritten")
    start_all(user)
    await user.should_see(marker="thread-row-0")
    await services.jobs.wait_until_idle()

    assert [call["lead"] for call in model.research_calls] == [
        "Lead A",
        "Lead B, rewritten",
        "Lead C",
    ]


async def test_an_emptied_lead_still_looks_empty_after_the_list_is_redrawn(
    user: User, model: RecordingModel
) -> None:
    await generate_leads(user)
    with user.scope(marker="lead-row-1"):
        user.find(kind=ui.input).clear()

    with user.scope(marker="lead-row-0"):
        user.find(marker="remove-lead").click()
    await user.should_not_see("Lead A")

    assert lead_boxes(user) == ["", "Lead C"]
    with user.scope(marker="lead-row-0"):
        user.find(marker="go").click()
    await user.should_see("This lead is empty. Fill it in first.")
    assert model.research_calls == []


# -- changes made in another tab -------------------------------------------------------------


async def test_threads_launched_elsewhere_appear_on_an_open_check_page(
    user: User, services: Services
) -> None:
    await generate_leads(user)
    (check,) = services.store.list_checks()

    services.checks.launch(check.id, ["vendor/research-model"])

    await user.should_see(marker="thread-row-0")
    with user.scope(marker="thread-row-2"):
        await user.should_see("Lead C")
        await user.should_see("Finished")
    await user.should_not_see(marker="lead-row-0")
    await user.should_not_see(marker="go")


async def test_removing_a_lead_already_removed_elsewhere_refreshes_the_list(
    user: User, services: Services
) -> None:
    await generate_leads(user)
    (check,) = services.store.list_checks()
    _, lead_b, _ = services.store.list_draft_leads(check.id)
    services.checks.remove_lead(lead_b.id)

    with user.scope(marker="lead-row-1"):
        user.find(marker="remove-lead").click()

    await user.should_see(OUT_OF_DATE)
    await user.should_not_see("Lead B")
    assert lead_boxes(user) == ["Lead A", "Lead C"]


async def test_go_on_a_lead_removed_elsewhere_refreshes_the_list(
    user: User, model: RecordingModel, services: Services
) -> None:
    await generate_leads(user)
    (check,) = services.store.list_checks()
    for lead in services.store.list_draft_leads(check.id):
        services.checks.remove_lead(lead.id)

    with user.scope(marker="lead-row-0"):
        user.find(marker="go").click()

    await user.should_see(OUT_OF_DATE)
    await user.should_not_see(marker="lead-row-0")
    await user.should_not_see(marker="go")
    assert model.research_calls == []


# -- storage failures are reported, and leave nothing half-done -------------------------------


async def test_a_check_that_cannot_be_saved_says_so(
    user: User, services: Services, faults: Faults
) -> None:
    faults.fail("INTO checks", times=None)
    await user.open("/")
    user.find(marker="composer").type(TEXT)

    user.find("Generate leads").click()

    await user.should_see("Something went wrong and nothing was saved. Please try again.")
    await user.should_see(marker="composer")
    assert services.store.list_checks() == []


async def test_research_that_cannot_be_started_says_so(
    user: User, model: RecordingModel, services: Services, faults: Faults
) -> None:
    await generate_leads(user)
    faults.fail("INTO jobs", times=None)

    start_all(user)

    await user.should_see("Research could not be started. Nothing was changed.")
    await user.should_not_see(marker="thread-row-0")
    assert lead_boxes(user) == ["Lead A", "Lead B", "Lead C"]
    assert model.research_calls == []


# -- evidence always shows where it really comes from -----------------------------------------


async def open_first_report(user: User) -> None:
    await generate_leads(user)
    start_all(user)
    await user.should_see(marker="thread-row-0")
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    user.find(marker="thread-row-0").click()
    await user.should_see("Findings")


async def test_a_link_written_with_a_title_goes_to_the_address_it_was_given(
    user: User, model: RecordingModel
) -> None:
    model.reports["Lead A"] = Report(
        notes="[Reuters: official statement](https://evil.example/statement?id=1) says so."
    )

    await open_first_report(user)

    (link,) = user.find(kind=ui.link, content="Reuters: official statement").elements
    assert link.props["href"] == "https://evil.example/statement?id=1"
    assert link.props["target"] == "_blank"


async def test_links_the_search_never_returned_are_listed_under_the_findings(
    user: User, model: RecordingModel
) -> None:
    model.reports["Lead A"] = Report(
        notes="See https://example.net/page and https://made-up.example/proof.",
        unreturned_links=["https://made-up.example/proof"],
    )

    await open_first_report(user)

    with user.scope(marker="unreturned-links"):
        await user.should_see("Links the search did not return")
        await user.should_see(kind=ui.label, content="https://made-up.example/proof")
        await user.should_not_see("https://example.net/page")


async def test_findings_with_every_link_returned_carry_no_warning(user: User) -> None:
    await open_first_report(user)

    await user.should_not_see(marker="unreturned-links")
