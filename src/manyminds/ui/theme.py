"""The look of the app: one typeface, near-monochrome, generous space, hairlines not boxes.

Colour is reserved for the small status dot. The system font is used so that nothing is
fetched from a font server.
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime

from nicegui import ui

from manyminds.core.models import Check, ThreadStatus

STATUS_TEXT = {
    ThreadStatus.QUEUED: "Queued",
    ThreadStatus.WORKING: "Working",
    ThreadStatus.FINISHED: "Finished",
    ThreadStatus.FAILED: "Failed",
}

# Class names used by the pages. Their rules are in CSS below.
TITLE = "mm-title"
HEADLINE = "mm-headline"
SECTION = "mm-section"
MUTED = "mm-muted"
BODY = "mm-body"
SOURCE = "mm-source"
QUOTE = "mm-quote"
LINK = "mm-link"
PANEL = "mm-panel"
LABEL = "mm-label"
QUIET = "mm-quiet"
NOTICE = "mm-notice"
ERROR = "mm-error"
RULED = "mm-ruled"
BUTTON = "mm-button"

CSS = """
:root {
    --mm-paper: #ffffff;
    --mm-ink: #1d1d1f;
    --mm-secondary: #6e6e73;
    --mm-tertiary: #a1a1a6;
    --mm-hairline: #e3e3e8;
    --mm-surface: #f5f5f7;
    --mm-queued: #a1a1a6;
    --mm-working: #2f6fde;
    --mm-finished: #2e9d62;
    --mm-failed: #c9372c;
    --mm-notice: #9a5b00;
    --mm-supports: #2e9d62;
    --mm-undermines: #c9642c;
    --mm-open: #f7f3ea;
    --mm-column: 880px;
    --mm-radius: 14px;
}
body, .q-field, .q-btn, .q-item {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", "Helvetica Neue",
        Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
}
body { background: var(--mm-paper); color: var(--mm-ink); }
.nicegui-content { padding: 0; }
.nicegui-sub-pages { width: 100%; }

/* Sidebar: the list of saved checks. */
.mm-sidebar { background: var(--mm-surface) !important; padding: 26px 14px; gap: 0; }
.mm-wordmark { font-size: 15px; font-weight: 600; letter-spacing: -0.01em; padding: 0 10px; }
.mm-new.q-btn {
    margin: 18px 0 22px; width: 100%; border-radius: 10px; min-height: 38px;
    background: var(--mm-paper) !important; color: var(--mm-ink) !important;
    border: 1px solid var(--mm-hairline); font-size: 14px; font-weight: 500;
    text-transform: none; letter-spacing: 0; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
.mm-new.q-btn:hover { border-color: #cfcfd6; }
.mm-side-heading {
    font-size: 12px; font-weight: 600; color: var(--mm-tertiary); padding: 0 10px 6px;
}
.mm-side-list { gap: 2px; align-items: stretch; width: 100%; }
.mm-side-item.q-item { padding: 8px 10px; min-height: 0; border-radius: 9px; }
.mm-side-item.q-item:hover { background: #ebebef; }
.mm-side-item .q-focus-helper { display: none; }
.mm-side-title {
    font-size: 14px; line-height: 1.35; color: var(--mm-ink);
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    overflow-wrap: anywhere;
}
.mm-side-date { font-size: 12px; color: var(--mm-tertiary); margin-top: 2px; }
.mm-side-item .q-item__section--side { padding-left: 6px; }
.mm-side-delete.q-btn { opacity: 0; transition: opacity 0.15s ease; }
.mm-side-item:hover .mm-side-delete.q-btn, .mm-side-delete.q-btn:focus-visible { opacity: 1; }
.mm-side-empty { font-size: 13px; color: var(--mm-tertiary); padding: 2px 10px; }

/* One centred column for everything. */
.mm-column {
    width: 100%; max-width: var(--mm-column); margin: 0 auto;
    padding: 64px 32px 120px; gap: 0; align-items: stretch;
}
.mm-home { min-height: 78vh; justify-content: center; padding-top: 24px; max-width: 760px; }

.mm-headline {
    font-size: 34px; line-height: 1.15; font-weight: 600; letter-spacing: -0.022em;
    text-align: center; margin-bottom: 36px;
}
.mm-title { font-size: 30px; line-height: 1.2; font-weight: 600; letter-spacing: -0.02em; }
.mm-head { align-items: flex-start; justify-content: space-between; flex-wrap: nowrap; gap: 24px; }
.mm-section {
    font-size: 19px; font-weight: 600; letter-spacing: -0.01em; color: var(--mm-ink);
    margin: 52px 0 14px;
}
.mm-section-note { font-size: 13px; color: var(--mm-secondary); margin: -8px 0 14px; }
.mm-label { font-size: 12px; font-weight: 600; color: var(--mm-secondary); margin-bottom: 8px; }
.mm-muted { font-size: 13px; line-height: 1.5; color: var(--mm-secondary); }
.mm-body {
    font-size: 17px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere;
}
/* A tinted panel sets quoted or given material apart from what the app says. */
.mm-panel {
    background: var(--mm-surface); border-radius: var(--mm-radius); padding: 20px 24px;
    gap: 0; align-items: stretch; margin-top: 26px;
}
.mm-source {
    font-size: 16px; line-height: 1.6; color: #3a3a3c;
    white-space: pre-wrap; overflow-wrap: anywhere;
}
.mm-notice { font-size: 13px; color: var(--mm-notice); margin-top: 14px; }
.mm-error { font-size: 13px; color: var(--mm-failed); margin-top: 14px; }
.mm-link {
    font-size: 14px; color: var(--mm-ink); text-decoration: underline;
    text-decoration-color: #c9c9cf; text-underline-offset: 3px; overflow-wrap: anywhere;
}
.mm-link:hover { text-decoration-color: var(--mm-ink); }
.mm-back {
    font-size: 13px; color: var(--mm-secondary); text-decoration: none; margin-bottom: 18px;
}
.mm-back:hover { color: var(--mm-ink); }

/* The paste box: the one prominent object on the home page. */
.mm-composer {
    border: 1px solid var(--mm-hairline); border-radius: 22px; background: var(--mm-paper);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04), 0 12px 40px rgba(0, 0, 0, 0.06);
    padding: 10px 12px 12px 22px; gap: 0; align-items: stretch;
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
}
.mm-composer:focus-within {
    border-color: #d2d2d7;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05), 0 16px 48px rgba(0, 0, 0, 0.09);
}
.mm-composer textarea { font-size: 17px; line-height: 1.5; min-height: 84px; }
.mm-composer-foot { border-top: 1px solid var(--mm-hairline); padding-top: 8px; margin-top: 4px; }
.mm-field .q-field__control::before, .mm-field .q-field__control::after { display: none; }
.mm-field .q-field__native, .mm-field .q-field__input { color: var(--mm-ink); }
.mm-field ::placeholder { color: var(--mm-tertiary); opacity: 1; }

/* Buttons: one filled shape for the main action, quiet ones for the rest. */
.mm-button.q-btn {
    background: var(--mm-ink) !important; color: var(--mm-paper) !important;
    border-radius: 999px; padding: 4px 22px; min-height: 40px;
    font-size: 14px; font-weight: 500; text-transform: none; letter-spacing: 0;
}
.mm-button.q-btn.disabled { opacity: 0.35 !important; }
.mm-quiet.q-btn {
    color: var(--mm-secondary) !important; border-radius: 999px; padding: 2px 14px;
    min-height: 34px; font-size: 13px; font-weight: 500; text-transform: none;
    letter-spacing: 0; border: 1px solid var(--mm-hairline); white-space: nowrap;
}
.mm-quiet.q-btn:hover { color: var(--mm-ink) !important; border-color: #cfcfd6; }
.mm-danger.q-btn { background: var(--mm-failed) !important; }
.mm-icon.q-btn { color: var(--mm-tertiary); }
.mm-icon.q-btn:hover { color: var(--mm-ink); }

/* Leads: each one is a field you can type in, and looks like one. */
.mm-leads { gap: 10px; align-items: stretch; }
.mm-lead {
    padding: 4px 8px 4px 16px; gap: 10px; align-items: flex-start; flex-wrap: nowrap;
    width: 100%; background: var(--mm-paper); border: 1px solid var(--mm-hairline);
    border-radius: 12px; transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.mm-lead:hover { border-color: #cfcfd6; }
.mm-lead:focus-within { border-color: var(--mm-ink); box-shadow: 0 0 0 3px rgba(29, 29, 31, 0.07); }
.mm-lead textarea { font-size: 16px; line-height: 1.5; padding: 8px 0; }
.mm-lead .mm-icon { margin-top: 6px; }
.mm-add.q-btn {
    width: 100%; margin-top: 10px; border: 1px dashed #cfcfd6; border-radius: 12px;
    min-height: 44px; color: var(--mm-secondary) !important; font-size: 14px; font-weight: 500;
    text-transform: none; letter-spacing: 0;
}
.mm-add-alone.q-btn { margin-top: 28px; }
.mm-add.q-btn:hover { color: var(--mm-ink) !important; border-color: var(--mm-ink); }
.mm-launch {
    margin-top: 18px; align-items: center; justify-content: space-between; flex-wrap: nowrap;
    background: var(--mm-surface); border-radius: var(--mm-radius); padding: 12px 12px 12px 20px;
    gap: 16px;
}
.mm-launch-label { font-size: 14px; color: var(--mm-secondary); white-space: nowrap; }
.mm-picker { min-width: 260px; flex: 1 1 auto; }
.mm-picker .q-field__control {
    border-radius: 999px; padding: 0 16px; min-height: 40px; background: var(--mm-paper);
}

/* The check page: a conversation that scrolls, with the box to write in fixed beneath it. */
.mm-chat-page { flex: 1 1 auto; min-height: 0; gap: 0; align-items: stretch; flex-wrap: nowrap; }
.mm-chat-title {
    font-size: 20px; line-height: 1.3; font-weight: 600; letter-spacing: -0.012em;
    overflow-wrap: anywhere; padding-top: 4px;
}
.mm-chat {
    flex: 1 1 auto; min-height: 0; width: 100%; margin-top: 18px;
    border-top: 1px solid var(--mm-hairline);
}
.mm-chat .q-scrollarea__content { width: 100%; padding: 0; }
.mm-chat-body { gap: 30px; padding: 30px 20px 36px 0; align-items: stretch; width: 100%; }
.mm-turn { gap: 14px; align-items: stretch; width: 100%; }
.mm-turn-user { align-items: flex-end; }
/* What the user said sits to the right in a tinted shape; replies are plain, to the left. */
.mm-bubble {
    background: var(--mm-surface); border-radius: 20px 20px 6px 20px; padding: 14px 20px;
    max-width: 84%; font-size: 16px; line-height: 1.55; color: var(--mm-ink);
    white-space: pre-wrap; overflow-wrap: anywhere;
}
.mm-say { font-size: 16px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
.mm-say-note { font-size: 14px; line-height: 1.5; color: var(--mm-secondary); }
.mm-read {
    background: var(--mm-surface); border-radius: 12px; padding: 14px 18px; gap: 0;
    align-items: stretch;
}
.mm-read-text {
    font-size: 14px; line-height: 1.6; color: #48484a; white-space: pre-wrap;
    overflow-wrap: anywhere;
}
.mm-hidden { display: none !important; }
/* Images waiting to be sent, and images already sent. */
.mm-tray { gap: 8px; padding: 8px 0 2px; }
.mm-chip {
    align-items: center; gap: 8px; flex-wrap: nowrap; padding: 4px 6px 4px 4px;
    background: var(--mm-surface); border-radius: 10px; max-width: 240px;
}
.mm-chip-thumb { width: 36px; height: 36px; border-radius: 7px; flex: none; }
.mm-chip-name {
    font-size: 13px; color: var(--mm-secondary); overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap;
}
.mm-attached {
    width: 280px; max-width: 84%; border-radius: 14px; border: 1px solid var(--mm-hairline);
}
.mm-read-as {
    font-size: 13px; line-height: 1.5; color: var(--mm-secondary); max-width: 84%;
    text-align: right; overflow-wrap: anywhere;
}
.mm-pending { align-items: center; gap: 10px; }
.mm-steps { gap: 8px; align-items: stretch; }
.mm-steps:empty { display: none; }
.mm-how.q-expansion-item { margin: -4px 0; }
.mm-how .q-item { padding: 0; min-height: 28px; font-size: 13px; color: var(--mm-secondary); }
.mm-how .q-item__section--side { padding-left: 6px; min-width: 0; }
.mm-how .q-expansion-item__content { padding: 8px 0 4px; }
.mm-how .q-focus-helper { display: none; }
.mm-reply-error { font-size: 14px; line-height: 1.5; color: var(--mm-failed); }
.mm-go.q-btn {
    background: var(--mm-ink) !important; color: var(--mm-paper) !important;
    border-radius: 999px; padding: 0 16px; min-height: 30px; margin-top: 7px;
    font-size: 13px; font-weight: 500; text-transform: none; letter-spacing: 0; flex: none;
}
.mm-go.q-btn:hover { background: #3a3a3c !important; }
.mm-group-foot { align-items: center; gap: 10px; flex-wrap: nowrap; width: 100%; }
.mm-group-foot .mm-add.q-btn { margin-top: 0; flex: 1 1 auto; width: auto; min-height: 38px; }
.mm-chevron { color: var(--mm-tertiary); font-size: 20px; }
.mm-leads .mm-thread.q-item { align-items: center; padding: 12px 10px 12px 16px; }
.mm-leads .mm-thread .q-item__section--side { padding-top: 0; padding-left: 14px; }
.mm-chat-notice { margin: 0 0 8px; }
.mm-chat-composer {
    margin: 10px 0 24px; border-radius: 20px; padding: 6px 10px 10px 20px; flex: none;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04), 0 8px 28px rgba(0, 0, 0, 0.06);
}
.mm-chat-composer textarea { font-size: 16px; min-height: 0; max-height: 30vh; }
.mm-chat-composer .mm-composer-foot { border-top: none; margin-top: 0; padding-top: 2px; }
.mm-chat-composer .mm-picker { min-width: 0; flex: 0 1 auto; }
.mm-chat-composer .mm-picker .q-field__control {
    background: none; padding: 0; min-height: 32px; border-radius: 0;
}
.mm-chat-composer .mm-picker .q-field__native { font-size: 14px; color: var(--mm-ink); }
.mm-chat-composer .mm-picker .q-field__control::before,
.mm-chat-composer .mm-picker .q-field__control::after { display: none; }
.mm-chat-composer .mm-button.q-btn { min-height: 36px; padding: 2px 20px; }

/* Threads: one card per lead being researched. */
.mm-threads { padding: 0; }
.mm-threads > .mm-thread + .mm-thread { margin-top: 10px; }
.mm-thread.q-item {
    padding: 16px 18px; min-height: 0; align-items: flex-start;
    border: 1px solid var(--mm-hairline); border-radius: 12px; background: var(--mm-paper);
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.mm-thread.q-item:hover { border-color: #cfcfd6; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05); }
.mm-thread .q-focus-helper { display: none; }
.mm-thread-text { font-size: 16px; line-height: 1.5; overflow-wrap: anywhere; }
.mm-thread .q-item__section--side { padding-left: 20px; padding-top: 3px; }

/* Status: a small coloured dot and a quiet word. */
.mm-status {
    font-size: 13px; color: var(--mm-secondary); white-space: nowrap;
    display: inline-flex; align-items: center; gap: 7px;
}
.mm-status::before {
    content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--mm-queued);
}
.mm-status-working::before {
    background: var(--mm-working); animation: mm-pulse 1.4s ease-in-out infinite;
}
.mm-status-finished::before { background: var(--mm-finished); }
.mm-status-failed::before { background: var(--mm-failed); }
@keyframes mm-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }
@media (prefers-reduced-motion: reduce) { .mm-status-working::before { animation: none; } }

/* Report: a summary, then evidence grouped and colour-ruled by which way it cuts. */
.mm-report-heading {
    font-size: 22px; font-weight: 600; letter-spacing: -0.015em; margin: 8px 0 4px;
}
.mm-stance { gap: 0; align-items: stretch; }
.mm-stance-heading {
    font-size: 15px; font-weight: 600; margin: 36px 0 12px;
    display: flex; align-items: center; gap: 9px;
}
.mm-stance-heading::before { content: ""; width: 9px; height: 9px; border-radius: 50%; }
.mm-stance-supports .mm-stance-heading::before { background: var(--mm-supports); }
.mm-stance-undermines .mm-stance-heading::before { background: var(--mm-undermines); }
.mm-stance-items { gap: 12px; align-items: stretch; }
.mm-evidence {
    padding: 16px 20px; gap: 10px; align-items: stretch; background: var(--mm-paper);
    border: 1px solid var(--mm-hairline); border-left-width: 3px; border-radius: 12px;
}
.mm-stance-supports .mm-evidence { border-left-color: var(--mm-supports); }
.mm-stance-undermines .mm-evidence { border-left-color: var(--mm-undermines); }
.mm-quote { font-size: 17px; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
.mm-open { background: var(--mm-open); }
.mm-usage { margin-top: 22px; color: var(--mm-tertiary); }
.mm-flag {
    font-size: 12px; font-weight: 500; color: var(--mm-notice); background: #fbf1dc;
    border-radius: 6px; padding: 2px 8px; align-self: flex-start;
}
.mm-host { font-size: 13px; color: var(--mm-tertiary); }
.mm-unchecked { font-size: 12px; color: var(--mm-tertiary); }

/* Thread page: a fixed heading with the transcript scrolling beneath it. */
.mm-tall { height: 100vh; padding-top: 48px; padding-bottom: 0; flex-wrap: nowrap; }
.mm-thread-page {
    flex: 1 1 auto; min-height: 0; gap: 0; align-items: stretch; flex-wrap: nowrap;
}
.mm-transcript {
    flex: 1 1 auto; min-height: 0; width: 100%; margin-top: 22px;
    border-top: 1px solid var(--mm-hairline);
}
.mm-transcript .q-scrollarea__content { width: 100%; padding: 0; }
.mm-transcript-body { gap: 14px; padding: 26px 20px 96px 0; align-items: stretch; width: 100%; }
.mm-step {
    font-size: 13px; line-height: 1.5; color: var(--mm-secondary); overflow-wrap: anywhere;
    display: flex; align-items: baseline; gap: 10px;
}
.mm-step::before {
    content: ""; flex: none; width: 6px; height: 6px; border-radius: 50%;
    background: #cfcfd6; transform: translateY(-1px);
}
.mm-passage {
    gap: 6px; align-items: stretch; background: var(--mm-surface);
    border-radius: 12px; padding: 14px 18px;
}
.mm-passage-message { background: none; padding: 4px 0; }
.mm-passage-heading { font-size: 12px; font-weight: 600; color: var(--mm-secondary); }
.mm-passage-text {
    font-size: 15px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere;
}
.mm-passage-thinking .mm-passage-text, .mm-passage-sources_found .mm-passage-text {
    color: #48484a; font-size: 14px;
}
.mm-report {
    gap: 0; align-items: stretch; margin-top: 22px; padding: 30px 34px 34px;
    border: 1px solid var(--mm-hairline); border-radius: 18px; background: var(--mm-paper);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03), 0 10px 34px rgba(0, 0, 0, 0.05);
}

.mm-dialog { padding: 26px 28px 20px; border-radius: 18px; gap: 8px; min-width: 340px; }
.mm-dialog-title { font-size: 18px; font-weight: 600; }

:focus-visible { outline: 2px solid var(--mm-ink); outline-offset: 2px; border-radius: 4px; }
.q-field :focus-visible { outline: none; }
@media (max-width: 720px) {
    .mm-column { padding: 40px 18px 96px; }
    .mm-report { padding: 22px 18px 24px; }
    .mm-launch { flex-wrap: wrap; }
}
"""


def apply() -> None:
    """Install the stylesheet and colours for the current page."""
    ui.colors(primary="#1d1d1f", secondary="#6e6e73", accent="#2f6fde", negative="#c9372c")
    ui.add_css(CSS)


def format_when(moment: datetime) -> str:
    """A date and time for display, such as "3 Nov 2026, 09:05", the same on every platform."""
    return f"{moment.day} {moment:%b %Y, %H:%M}"


def sidebar(saved_checks: Callable[[], object]) -> None:
    """The left column: a way to start a check, and every check that has been saved."""
    with ui.left_drawer(bordered=False).props("width=264").classes("mm-sidebar"):
        ui.label("manyminds").classes("mm-wordmark")
        ui.button("New check", icon="add", on_click=lambda: ui.navigate.to("/")).props(
            "flat no-caps"
        ).classes("mm-new")
        ui.label("Checks").classes("mm-side-heading")
        saved_checks()


def sidebar_checks(checks: Sequence[Check], ask_delete: Callable[[str], object]) -> None:
    """The saved checks, newest first. Titles come from a model, so they are plain text."""
    if not checks:
        ui.label("No checks yet").classes("mm-side-empty")
        return
    with ui.list().classes("mm-side-list"):
        for index, check in enumerate(checks):
            target = f"/check/{check.id}"
            with (
                ui.item(on_click=lambda target=target: ui.navigate.to(target))
                .props("clickable")
                .classes("mm-side-item")
                .mark(f"sidebar-check-{index}")
            ):
                with ui.item_section():
                    ui.label(check.title).classes("mm-side-title")
                    ui.label(format_when(check.created_at.astimezone())).classes("mm-side-date")
                with ui.item_section().props("side"):
                    # The click must not also open the check.
                    (
                        ui.button(icon="delete_outline")
                        .on("click.stop", lambda check_id=check.id: ask_delete(check_id))
                        .props('flat round dense size=sm aria-label="Delete check"')
                        .classes("mm-icon mm-side-delete")
                        .mark(f"sidebar-delete-{index}")
                    )


@contextmanager
def content(*, home: bool = False, tall: bool = False) -> Iterator[None]:
    """The single centred column every page puts its content in.

    A tall column fills the window exactly, for a page with its own scrolling area.
    """
    extra = (" mm-home" if home else "") + (" mm-tall" if tall else "")
    with ui.column().classes("mm-column" + extra):
        yield


def status_label(status: ThreadStatus) -> ui.label:
    label = ui.label()
    set_status(label, status)
    return label


def set_status(label: ui.label, status: ThreadStatus) -> None:
    """Change a status label in place, so the row it sits in is not rebuilt."""
    label.set_text(STATUS_TEXT[status])
    label.classes(replace=f"mm-status mm-status-{status.value}")
