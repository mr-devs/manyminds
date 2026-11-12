"""Builds and serves the interface."""

from collections.abc import Callable
from typing import Any

from nicegui import Event, native
from nicegui import app as app
from nicegui import ui as ui
from starlette.middleware.trustedhost import TrustedHostMiddleware

from manyminds.core.events import JobUpdated
from manyminds.core.services import Services
from manyminds.ui import pages, theme

LOCALHOST = "127.0.0.1"
ALLOWED_HOSTS = [LOCALHOST, "localhost"]


def install_host_check(served: Any) -> None:
    """Refuse requests whose Host header names anything but this machine.

    Binding to localhost keeps other machines out; this also stops a web page elsewhere from
    reaching the app by pointing its own domain name at 127.0.0.1.
    """
    served.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


def build_root(services: Services) -> Callable[[], None]:
    """Return the function NiceGUI calls to build the page for each browser tab."""
    updates: Event[JobUpdated] = Event()
    services.bus.subscribe(updates.emit)

    def home() -> None:
        pages.home_page(services)

    def check(check_id: str) -> None:
        pages.check_page(services, updates, check_id)

    def thread(check_id: str, thread_id: str) -> None:
        pages.thread_page(services, updates, check_id, thread_id)

    def root() -> None:
        theme.apply()
        theme.sidebar()
        ui.sub_pages(
            {
                "/": home,
                "/check/{check_id}": check,
                "/check/{check_id}/thread/{thread_id}": thread,
            }
        )

    return root


def run(services: Services, *, port: int | None = None, show: bool = True) -> None:
    """Serve the app on this machine only."""
    install_host_check(app)
    ui.run(
        build_root(services),
        host=LOCALHOST,
        port=port or native.find_open_port(),
        reload=False,
        show=show,
        title="manyminds",
        favicon="🔎",
    )
