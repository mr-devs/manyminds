"""Interface behaviours pinned down after the milestone 1a independent review."""

from nicegui import ui
from nicegui.testing import User

from manyminds.core.services import Services
from support import RecordingModel

TEXT = "The bridge opened in 1932."


async def generate_leads(user: User) -> None:
    await user.open("/")
    user.find(marker="composer").type(TEXT)
    user.find("Generate leads").click()
    await user.should_see("Leads to research")


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


async def test_a_stale_lead_list_cannot_damage_launched_threads(
    user: User, services: Services
) -> None:
    await generate_leads(user)
    (check,) = services.store.list_checks()
    # The leads are launched from elsewhere (another tab) while this page still shows them.
    threads = services.checks.launch(check.id, ["vendor/research-model"])
    await services.jobs.wait_until_idle()

    with user.scope(marker="lead-row-0"):
        user.find(marker="remove-lead").click()

    await user.should_see("These leads have already been launched.")
    await user.should_not_see(marker="lead-row-0")
    assert services.store.list_threads(check.id) == threads
    assert all(services.store.get_report(services.store.list_jobs(t.id)[0].id) for t in threads)
