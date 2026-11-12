"""Shows a report: summary, quoted evidence with links, and what stayed unknown.

Everything a model wrote is shown as plain text. It is never rendered as HTML or markdown,
and nothing here loads an image, so retrieved content cannot inject markup or leak data.
"""

from nicegui import ui

from manyminds.core.models import EvidenceItem, Report, Stance
from manyminds.ui import theme

GROUPS = (
    (Stance.SUPPORTS, "Supports the lead", "evidence-supports"),
    (Stance.UNDERMINES, "Undermines the lead", "evidence-undermines"),
)


def _evidence_item(item: EvidenceItem) -> None:
    with ui.column().classes("gap-1 border-l-4 border-slate-200 pl-4 py-1"):
        ui.label(item.quote).classes(theme.BODY + " italic")
        ui.link(item.title or item.url, item.url, new_tab=True).classes(
            "text-sm text-sky-800 break-all"
        )
        if not item.grounded:
            ui.label("Not found in search results").classes("text-xs font-medium text-amber-700")


def report_view(report: Report) -> None:
    ui.label("Summary").classes(theme.SECTION)
    ui.label(report.summary).classes(theme.BODY)

    if not report.evidence:
        ui.label("Evidence").classes(theme.SECTION)
        ui.label("No evidence was found.").classes(theme.MUTED)
    for stance, heading, marker in GROUPS:
        items = [item for item in report.evidence if item.stance is stance]
        if items:
            with ui.column().classes("gap-3 items-stretch").mark(marker):
                ui.label(heading).classes(theme.SECTION)
                for item in items:
                    _evidence_item(item)

    ui.label("Could not be determined").classes(theme.SECTION)
    ui.label(report.undetermined).classes(theme.BODY)
