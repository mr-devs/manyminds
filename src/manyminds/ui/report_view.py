"""Shows a report: summary, quoted evidence with links, and what stayed unknown.

Everything a model wrote is shown as plain text. It is never rendered as HTML or markdown,
and nothing here loads an image, so retrieved content cannot inject markup or leak data.
"""

from urllib.parse import urlsplit

from nicegui import ui

from manyminds.core.models import EvidenceItem, Report, Stance, Usage
from manyminds.ui import theme

GROUPS = (
    (Stance.SUPPORTS, "Supports the lead", "evidence-supports"),
    (Stance.UNDERMINES, "Undermines the lead", "evidence-undermines"),
)


def _evidence_item(item: EvidenceItem) -> None:
    with ui.column().classes("mm-evidence"):
        ui.label(item.quote).classes(theme.QUOTE)
        with ui.row().classes("items-baseline gap-2"):
            ui.link(item.title or item.url, item.url, new_tab=True).classes(theme.LINK)
            if item.title:
                # A title is whatever the model wrote, so the real host is always shown too.
                ui.label(urlsplit(item.url).hostname or "").classes("mm-host")
        if not item.grounded:
            ui.label("Not found in search results").classes("mm-flag")
        elif item.quote_matched is False:
            ui.label("Quote not found in the search result").classes("mm-flag")


def report_view(report: Report) -> None:
    ui.label("Summary").classes(theme.SECTION)
    ui.label(report.summary).classes(theme.BODY)

    if not report.evidence:
        ui.label("Evidence").classes(theme.SECTION)
        ui.label("No evidence was found.").classes(theme.MUTED)
    for stance, heading, marker in GROUPS:
        items = [item for item in report.evidence if item.stance is stance]
        if items:
            with ui.column().classes("gap-0 items-stretch").mark(marker):
                ui.label(heading).classes(theme.SECTION)
                with ui.column().classes("gap-0 items-stretch " + theme.RULED):
                    for item in items:
                        _evidence_item(item)

    ui.label("Could not be determined").classes(theme.SECTION)
    ui.label(report.undetermined).classes(theme.BODY)


def usage_line(usage: Usage | None) -> str | None:
    """What a job used, as one line, or None when there is nothing to report."""
    if usage is None or not (usage.searches or usage.input_tokens or usage.output_tokens):
        return None
    searches = "1 search" if usage.searches == 1 else f"{usage.searches} searches"
    tokens = usage.input_tokens + usage.output_tokens
    return f"{searches}, {tokens:,} tokens, ${usage.cost:.4f}"
