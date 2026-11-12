"""The home page says where text goes, and a finished thread shows what it used."""

from __future__ import annotations

from nicegui.testing import User, user_simulation

from manyminds.core.models import Usage
from manyminds.core.services import build_services
from manyminds.core.storage import Store
from manyminds.ui.app import build_root
from support import RecordingModel

NOTICE = "Text you paste is sent to OpenRouter, the model provider and the Exa search engine."


async def open_thread(user: User, row: int) -> None:
    await user.open("/")
    user.find(marker="composer").type("The bridge opened in 1932.")
    user.find("Generate leads").click()
    await user.should_see("Leads to research")
    user.find("Go").click()
    await user.should_see("Threads")
    with user.scope(marker=f"thread-row-{row}"):
        await user.should_see("Finished")
    user.find(marker=f"thread-row-{row}").click()
    await user.should_see("Started")


async def test_the_home_page_shows_the_notice() -> None:
    services = build_services(
        store=Store(":memory:"),
        model=RecordingModel(),
        research_models=["vendor/model-a"],
        decompose_model="vendor/fast-model",
        notice=NOTICE,
    )

    async with user_simulation(build_root(services)) as user:
        await user.open("/")

        await user.should_see(NOTICE)


async def test_a_finished_thread_shows_searches_tokens_and_cost(
    user: User, model: RecordingModel
) -> None:
    model.usages["Lead A"] = Usage(
        input_tokens=6772, output_tokens=1096, cost=0.00901378, searches=2
    )

    await open_thread(user, 0)

    await user.should_see("2 searches, 7,868 tokens, $0.0090")


async def test_one_search_is_singular(user: User, model: RecordingModel) -> None:
    model.usages["Lead A"] = Usage(input_tokens=10, output_tokens=5, cost=0.5, searches=1)

    await open_thread(user, 0)

    await user.should_see("1 search, 15 tokens, $0.5000")


async def test_a_thread_with_nothing_to_report_shows_no_usage_line(
    user: User, model: RecordingModel
) -> None:
    await open_thread(user, 1)

    await user.should_see("Findings about: Lead B")
    await user.should_not_see("tokens")
