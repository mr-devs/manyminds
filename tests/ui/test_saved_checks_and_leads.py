"""The sidebar lists saved checks, and leads can be added, and work retried or deleted."""

from __future__ import annotations

from nicegui import ui
from nicegui.testing import User, user_simulation

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind
from manyminds.core.services import Services
from manyminds.ui.app import build_root
from support import RecordingModel, until


async def new_check(user: User, text: str) -> None:
    await user.open("/")
    user.find(marker="composer").type(text)
    user.find("Generate leads").click()
    await user.should_see("Leads to research")


# -- sidebar -------------------------------------------------------------------------------


async def test_the_sidebar_lists_checks_newest_first(
    services: Services, model: RecordingModel
) -> None:
    model.title = "Older check"
    await services.checks.create_check("First text.")
    model.title = "Newer check"
    await services.checks.create_check("Second text.")

    async with user_simulation(build_root(services)) as user:
        await user.open("/")

        with user.scope(marker="sidebar-check-0"):
            await user.should_see("Newer check")
        with user.scope(marker="sidebar-check-1"):
            await user.should_see("Older check")


async def test_a_sidebar_entry_opens_its_check(services: Services, model: RecordingModel) -> None:
    model.title = "Older check"
    await services.checks.create_check("First text, the older one.")
    model.title = "Newer check"
    await services.checks.create_check("Second text.")

    async with user_simulation(build_root(services)) as user:
        await user.open("/")
        user.find(marker="sidebar-check-1").click()

        await user.should_see("First text, the older one.")
        await user.should_see("Leads to research")


async def test_a_new_check_appears_in_the_sidebar_at_once(user: User) -> None:
    await user.open("/")
    await user.should_not_see(marker="sidebar-check-0")

    await new_check(user, "The bridge opened in 1932.")

    with user.scope(marker="sidebar-check-0"):
        await user.should_see("Bridge claim")


async def test_an_empty_sidebar_says_so(user: User) -> None:
    await user.open("/")

    await user.should_see("No checks yet")


# -- adding leads ---------------------------------------------------------------------------


async def test_a_lead_can_be_added_and_researched(user: User, services: Services) -> None:
    await new_check(user, "The bridge opened in 1932.")

    user.find("Add a lead").click()
    await user.should_see(marker="lead-row-3")
    with user.scope(marker="lead-row-3"):
        user.find(kind=ui.input).type("A lead of my own")
    user.find("Go").click()
    await user.should_see("Threads")

    with user.scope(marker="thread-row-3"):
        await user.should_see("A lead of my own")


async def test_a_lead_can_be_added_after_research_has_started(
    user: User, services: Services
) -> None:
    await new_check(user, "The bridge opened in 1932.")
    user.find("Go").click()
    await user.should_see("Threads")
    await user.should_not_see(marker="lead-row-0")

    user.find("Add a lead").click()
    await user.should_see(marker="lead-row-0")
    with user.scope(marker="lead-row-0"):
        user.find(kind=ui.input).type("One more lead")
    user.find("Go").click()
    await user.should_see(marker="thread-row-3")

    with user.scope(marker="thread-row-3"):
        await user.should_see("One more lead")


async def test_adding_past_the_limit_explains_why(user: User, services: Services) -> None:
    await new_check(user, "The bridge opened in 1932.")
    (check,) = services.store.list_checks()
    for _ in range(22):
        services.checks.add_lead(check.id)

    user.find("Add a lead").click()

    await user.should_see("A list holds 25 leads at most. Research these, then add the rest.")
    assert len(services.store.list_draft_leads(check.id)) == 25


# -- deleting --------------------------------------------------------------------------------


async def test_a_check_can_be_deleted_after_confirming(user: User, services: Services) -> None:
    await new_check(user, "The bridge opened in 1932.")

    user.find("Delete check").click()
    await user.should_see("Delete this check and its research?")
    user.find(marker="confirm-delete").click()

    await user.should_see("What would you like to check?")
    await user.should_not_see(marker="sidebar-check-0")
    assert services.store.list_checks() == []


async def test_cancelling_keeps_the_check(user: User, services: Services) -> None:
    await new_check(user, "The bridge opened in 1932.")

    user.find("Delete check").click()
    await user.should_see("Delete this check and its research?")
    user.find("Cancel").click()

    assert len(services.store.list_checks()) == 1


# -- trying again ---------------------------------------------------------------------------


async def test_a_failed_thread_offers_to_try_again(
    user: User, services: Services, model: RecordingModel
) -> None:
    model.failures["Lead A"] = ModelError(ErrorKind.PROVIDER, "The provider fell over.")
    await new_check(user, "The bridge opened in 1932.")
    user.find("Go").click()
    await user.should_see("Threads")
    with user.scope(marker="thread-row-0"):
        await user.should_see("Failed")
    user.find(marker="thread-row-0").click()
    await user.should_see("Stopped: The provider fell over.")

    model.failures.clear()
    user.find("Try again").click()

    await user.should_see("Findings about: Lead A")
    await user.should_not_see("Try again")
    (check,) = services.store.list_checks()
    thread = services.store.list_threads(check.id)[0]
    await until(lambda: len(services.store.list_jobs(thread.id)) == 2)


async def test_a_finished_thread_does_not_offer_to_try_again(user: User) -> None:
    await new_check(user, "The bridge opened in 1932.")
    user.find("Go").click()
    await user.should_see("Threads")
    with user.scope(marker="thread-row-0"):
        await user.should_see("Finished")
    user.find(marker="thread-row-0").click()

    await user.should_see("Findings about: Lead A")
    await user.should_not_see("Try again")
