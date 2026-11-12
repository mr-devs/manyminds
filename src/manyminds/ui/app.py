"""Builds and serves the interface."""

import logging
from collections.abc import Callable
from typing import Any

from nicegui import Event, native
from nicegui import app as app
from nicegui import ui as ui
from starlette.middleware.trustedhost import TrustedHostMiddleware

from manyminds.core.checks import CheckBusyError
from manyminds.core.events import ChatUpdated, Update
from manyminds.core.services import Services
from manyminds.core.storage import NotFoundError
from manyminds.ui import pages, theme

logger = logging.getLogger(__name__)

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
    updates: Event[Update] = Event()
    services.bus.subscribe(updates.emit)

    def root() -> None:
        theme.apply()
        store = services.store
        viewing: dict[str, str | None] = {"check": None}
        listed: list[tuple[str, str]] = []

        def ask_delete(check_id: str) -> None:
            """Ask before deleting a check, from its own page or from the sidebar."""

            def delete() -> None:
                try:
                    services.checks.delete_check(check_id)
                except NotFoundError:
                    pass  # Already deleted from another tab; the outcome is the same.
                except CheckBusyError as error:
                    ui.notify(str(error))
                    return
                except Exception as error:
                    logger.error("Deleting a check failed: %s", type(error).__name__)
                    ui.notify("This check could not be deleted. Nothing was changed.")
                    return
                saved_checks.refresh()
                if viewing["check"] == check_id:
                    ui.navigate.to("/")

            dialogs.clear()
            with dialogs:
                pages.confirm_delete(delete).open()

        @ui.refreshable
        def saved_checks() -> None:
            checks = store.list_checks()
            listed[:] = [(check.id, check.title) for check in checks]
            theme.sidebar_checks(checks, ask_delete)

        def home() -> None:
            viewing["check"] = None
            pages.home_page(services, saved_checks.refresh)

        def check(check_id: str) -> None:
            viewing["check"] = check_id
            pages.check_page(services, updates, check_id, ask_delete)

        def thread(check_id: str, thread_id: str) -> None:
            viewing["check"] = check_id
            pages.thread_page(services, updates, check_id, thread_id)

        def keep_sidebar_current(event: Update) -> None:
            # A check's title arrives after the check does, and checks come and go in other tabs.
            if dialogs.is_deleted:
                updates.unsubscribe(keep_sidebar_current)
            elif isinstance(event, ChatUpdated) and listed != [
                (check.id, check.title) for check in store.list_checks()
            ]:
                saved_checks.refresh()

        theme.sidebar(saved_checks)
        dialogs = ui.element()
        updates.subscribe(keep_sidebar_current)
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
