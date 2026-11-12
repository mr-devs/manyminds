"""Shared look: neutral colours, a sidebar, and a centred content column."""

from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import ui

from manyminds.core.models import ThreadStatus

STATUS_TEXT = {
    ThreadStatus.QUEUED: "Queued",
    ThreadStatus.WORKING: "Working",
    ThreadStatus.FINISHED: "Finished",
    ThreadStatus.FAILED: "Failed",
}
STATUS_STYLE = {
    ThreadStatus.QUEUED: "text-slate-500",
    ThreadStatus.WORKING: "text-sky-700",
    ThreadStatus.FINISHED: "text-emerald-700",
    ThreadStatus.FAILED: "text-rose-700",
}

HEADING = "text-2xl font-medium text-slate-800"
SECTION = "text-xs font-semibold uppercase tracking-wider text-slate-500 mt-6"
MUTED = "text-sm text-slate-500"
BODY = "text-base text-slate-800 whitespace-pre-wrap break-words"


def apply_colours() -> None:
    ui.colors(primary="#334155", secondary="#64748b", accent="#0f766e", negative="#be123c")


def sidebar() -> None:
    with ui.left_drawer(bordered=True).classes("bg-slate-50 p-4 gap-2"):
        ui.label("manyminds").classes("text-lg font-semibold text-slate-800")
        ui.link("New check", "/").classes("text-slate-700 no-underline hover:underline")


@contextmanager
def content() -> Iterator[None]:
    """The centred column every page puts its content in."""
    with ui.column().classes("w-full max-w-3xl mx-auto px-4 py-8 gap-3 items-stretch"):
        yield


def status_label(status: ThreadStatus) -> ui.label:
    label = ui.label()
    set_status(label, status)
    return label


def set_status(label: ui.label, status: ThreadStatus) -> None:
    """Change a status label in place, so the row it sits in is not rebuilt."""
    label.set_text(STATUS_TEXT[status])
    label.classes(replace=f"text-sm font-medium {STATUS_STYLE[status]}")
