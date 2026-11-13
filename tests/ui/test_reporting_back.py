"""Threads report back in the main conversation, and the report follows once all are done."""

from nicegui import ElementFilter, ui
from nicegui.testing import User

from manyminds.core.errors import ModelError
from manyminds.core.models import ErrorKind, Report
from manyminds.core.services import Services
from support import RecordingModel, start_all, until

TEXT = "The bridge opened in 1932."


async def new_check(user: User) -> None:
    await user.open("/")
    user.find(marker="composer").type(TEXT)
    user.find("Generate leads").click()
    await user.should_see(marker="lead-list")


def handbacks(user: User) -> int:
    with user:
        return len(list(ElementFilter(marker="handback")))


async def test_each_thread_reports_back_in_the_conversation_with_its_findings(
    user: User, model: RecordingModel, services: Services
) -> None:
    model.reports["Lead A"] = Report(
        notes="## Findings\n\n**The archive** agrees: https://example.org/a",
        unreturned_links=["https://made-up.example/x"],
    )
    await new_check(user)

    with user.scope(marker="lead-row-0"):
        user.find(marker="go").click()
    await user.should_see(marker="handback")

    with user.scope(marker="handback"):
        await user.should_see("Lead A")
        await user.should_see("Finished")
        await user.should_see(marker="findings", content="The archive")
        await user.should_see("Links the search did not return")
        await user.should_see("https://made-up.example/x")
        await user.should_see("Open the thread to see its work")
        await user.should_not_see("## Findings")


async def test_a_thread_that_failed_reports_back_with_the_reason(
    user: User, model: RecordingModel
) -> None:
    model.failures["Lead A"] = ModelError(ErrorKind.PROVIDER, "The provider fell over.")
    await new_check(user)

    with user.scope(marker="lead-row-0"):
        user.find(marker="go").click()
    await user.should_see(marker="handback")

    with user.scope(marker="handback"):
        await user.should_see("Lead A")
        await user.should_see("Failed")
        await user.should_see("Stopped: The provider fell over.")
    await user.should_not_see(marker="final-report")


async def test_the_report_is_written_once_every_started_lead_has_finished(
    user: User, model: RecordingModel
) -> None:
    model.hold = True
    model.final_report = "## What was found\n\n**Both** leads agree on 1932."
    await new_check(user)
    start_all(user)
    await until(lambda: model.active == 2)

    model.release("Lead A")
    await until(lambda: handbacks(user) == 1)
    await user.should_not_see(marker="final-report")

    model.release_all()
    await user.should_see(marker="final-report")
    await user.should_see(marker="reply", content="What was found")
    await user.should_see(marker="reply", content="leads agree on 1932.")
    assert handbacks(user) == 3
    await user.should_not_see("## What was found")


async def test_writing_the_report_says_so_while_it_is_under_way(
    user: User, model: RecordingModel
) -> None:
    model.leads = ["Lead A"]
    model.hold_report = True
    await new_check(user)

    with user.scope(marker="lead-row-0"):
        user.find(marker="go").click()

    await user.should_see("Every lead has finished. Writing the report")
    model.release_report()
    await user.should_see(marker="reply", content="The report.")
    await user.should_not_see("Every lead has finished. Writing the report")


async def test_a_report_that_could_not_be_written_says_why(
    user: User, model: RecordingModel
) -> None:
    model.leads = ["Lead A"]
    model.report_error = ModelError(ErrorKind.CREDITS, "Your OpenRouter credit has run out.")
    await new_check(user)

    with user.scope(marker="lead-row-0"):
        user.find(marker="go").click()

    await user.should_see("The report could not be written: Your OpenRouter credit has run out.")


async def test_leads_proposed_by_the_report_can_be_started(
    user: User, model: RecordingModel, services: Services
) -> None:
    model.leads = ["Lead A"]
    model.report_leads = ["Who built the bridge?"]
    await new_check(user)
    with user.scope(marker="lead-row-0"):
        user.find(marker="go").click()
    await user.should_see(marker="final-report")

    await user.should_see(kind=ui.textarea, content="Who built the bridge?")
    with user.scope(marker="lead-row-0"):
        user.find(marker="go").click()
    await services.jobs.wait_until_idle()

    assert [call["lead"] for call in model.research_calls] == ["Lead A", "Who built the bridge?"]


async def test_the_hand_backs_and_the_report_are_there_when_the_check_is_opened_again(
    user: User, model: RecordingModel, services: Services
) -> None:
    model.leads = ["Lead A"]
    await new_check(user)
    with user.scope(marker="lead-row-0"):
        user.find(marker="go").click()
    await user.should_see(marker="final-report")
    (check,) = services.store.list_checks()

    await user.open("/")
    await user.open(f"/check/{check.id}")

    await user.should_see(marker="handback")
    await user.should_see(marker="final-report")
    await user.should_see(marker="reply", content="The report.")
