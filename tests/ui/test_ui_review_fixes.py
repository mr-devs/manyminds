"""Interface behaviours pinned down after independent reviews of milestone 1a."""

from nicegui import ElementFilter, ui
from nicegui.testing import User

from manyminds.core.models import EvidenceItem, Report, Stance
from manyminds.core.services import Services
from support import Faults, RecordingModel

TEXT = "The bridge opened in 1932."
OUT_OF_DATE = "This list was out of date and has been refreshed."


async def generate_leads(user: User) -> None:
    await user.open("/")
    user.find(marker="composer").type(TEXT)
    user.find("Generate leads").click()
    await user.should_see("Leads to research")


def lead_boxes(user: User) -> list[str]:
    with user:
        return [box.value for box in ElementFilter(kind=ui.textarea).within(marker="lead-list")]


# -- empty leads -----------------------------------------------------------------------------


async def test_go_is_refused_while_a_lead_is_empty(
    user: User, model: RecordingModel, services: Services
) -> None:
    await generate_leads(user)

    with user.scope(marker="lead-row-1"):
        user.find(kind=ui.input).clear()
    user.find("Go").click()

    await user.should_see("A lead is empty. Fill it in or remove it.")
    await user.should_not_see("Threads")
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
    user.find("Go").click()
    await user.should_see("Threads")
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
    user.find("Go").click()
    await user.should_see("A lead is empty. Fill it in or remove it.")
    assert model.research_calls == []


# -- changes made in another tab -------------------------------------------------------------


async def test_threads_launched_elsewhere_appear_on_an_open_check_page(
    user: User, services: Services
) -> None:
    await generate_leads(user)
    (check,) = services.store.list_checks()

    services.checks.launch(check.id, ["vendor/research-model"])

    await user.should_see("Threads")
    with user.scope(marker="thread-row-2"):
        await user.should_see("Lead C")
        await user.should_see("Finished")
    await user.should_not_see(marker="lead-row-0")
    await user.should_not_see("Go")


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


async def test_go_with_every_lead_removed_elsewhere_refreshes_the_list(
    user: User, model: RecordingModel, services: Services
) -> None:
    await generate_leads(user)
    (check,) = services.store.list_checks()
    for lead in services.store.list_draft_leads(check.id):
        services.checks.remove_lead(lead.id)

    user.find("Go").click()

    await user.should_see(OUT_OF_DATE)
    await user.should_not_see(marker="lead-row-0")
    await user.should_not_see("Go")
    assert model.research_calls == []


# -- storage failures are reported, and leave nothing half-done -------------------------------


async def test_a_check_that_cannot_be_saved_says_so(
    user: User, services: Services, faults: Faults
) -> None:
    faults.fail("INTO leads", times=None)
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

    user.find("Go").click()

    await user.should_see("Research could not be started. Nothing was changed.")
    await user.should_not_see("Threads")
    assert lead_boxes(user) == ["Lead A", "Lead B", "Lead C"]
    assert model.research_calls == []


# -- evidence always shows where it really comes from -----------------------------------------


async def open_first_report(user: User) -> None:
    await generate_leads(user)
    user.find("Go").click()
    await user.should_see("Threads")
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    user.find(marker="thread-row-0").click()
    await user.should_see("Summary")


async def test_a_titled_source_also_shows_its_real_host(user: User, model: RecordingModel) -> None:
    model.reports["Lead A"] = Report(
        summary="One source.",
        evidence=[
            EvidenceItem(
                url="https://evil.example/statement?id=1",
                title="Reuters: official statement",
                quote="A quoted passage.",
                stance=Stance.SUPPORTS,
                grounded=True,
            )
        ],
        undetermined="Everything else.",
    )

    await open_first_report(user)

    with user.scope(marker="evidence-supports"):
        await user.should_see(kind=ui.link, content="Reuters: official statement")
        await user.should_see(kind=ui.label, content="evil.example")


async def test_an_untitled_source_shows_its_address_once(user: User, model: RecordingModel) -> None:
    model.reports["Lead A"] = Report(
        summary="One source.",
        evidence=[
            EvidenceItem(
                url="https://example.net/page", quote="A quoted passage.", stance=Stance.SUPPORTS
            )
        ],
        undetermined="Everything else.",
    )

    await open_first_report(user)

    with user.scope(marker="evidence-supports"):
        await user.should_see(kind=ui.link, content="https://example.net/page")
    with user:
        hosts = [
            label.text for label in ElementFilter(kind=ui.label) if label.text == "example.net"
        ]
    assert hosts == []
