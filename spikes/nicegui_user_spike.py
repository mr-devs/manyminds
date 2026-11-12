"""Throwaway: does user_simulation + sub_pages + background updates work as hoped?"""

import asyncio

from nicegui import ui
from nicegui.testing import user_simulation

listeners = []


def root() -> None:
    with ui.left_drawer():
        ui.label("Sidebar")
    ui.sub_pages({"/": home, "/check/{check_id}": check})


def home() -> None:
    box = ui.textarea(placeholder="Paste text").mark("composer")

    async def go() -> None:
        await asyncio.sleep(0)
        ui.navigate.to(f"/check/{box.value}")

    ui.button("Generate leads", on_click=go)


def check(check_id: str) -> None:
    state = {"status": "queued"}

    @ui.refreshable
    def rows() -> None:
        ui.label(f"check {check_id}: {state['status']}")

    rows()

    def on_event(status: str) -> None:
        state["status"] = status
        rows.refresh()

    listeners.append(on_event)


async def test_spike() -> None:
    async with user_simulation(root) as user:
        await user.open("/")
        await user.should_see("Sidebar")
        user.find(marker="composer").type("abc")
        user.find("Generate leads").click()
        await user.should_see("check abc: queued")

        async def later() -> None:
            await asyncio.sleep(0.05)
            for listener in listeners:
                listener("finished")

        task = asyncio.create_task(later())
        await user.should_see("check abc: finished")
        await task
