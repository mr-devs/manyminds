"""The look of the app: one typeface, near-monochrome, generous space, hairlines not boxes.

Colour is reserved for the small status dot. The system font is used so that nothing is
fetched from a font server.
"""

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

# Class names used by the pages. Their rules are in CSS below.
TITLE = "mm-title"
HEADLINE = "mm-headline"
SECTION = "mm-section"
MUTED = "mm-muted"
BODY = "mm-body"
SOURCE = "mm-source"
QUOTE = "mm-quote"
LINK = "mm-link"
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
    --mm-hairline: #e6e6ea;
    --mm-surface: #f6f6f7;
    --mm-queued: #a1a1a6;
    --mm-working: #2f6fde;
    --mm-finished: #2e9d62;
    --mm-failed: #c9372c;
    --mm-notice: #9a5b00;
    --mm-column: 680px;
}
body, .q-field, .q-btn, .q-item {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", "Helvetica Neue",
        Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
}
body { background: var(--mm-paper); color: var(--mm-ink); }
.nicegui-content { padding: 0; }
.nicegui-sub-pages { width: 100%; }

/* Sidebar: present but quiet. */
.mm-sidebar { background: var(--mm-surface) !important; padding: 28px 22px; gap: 22px; }
.mm-wordmark { font-size: 15px; font-weight: 600; letter-spacing: -0.01em; }
.mm-nav { font-size: 14px; color: var(--mm-secondary); text-decoration: none; }
.mm-nav:hover { color: var(--mm-ink); }

/* One centred column for everything. */
.mm-column {
    width: 100%; max-width: var(--mm-column); margin: 0 auto;
    padding: 72px 24px 120px; gap: 0; align-items: stretch;
}
.mm-home { min-height: 78vh; justify-content: center; padding-top: 24px; }

.mm-headline {
    font-size: 34px; line-height: 1.15; font-weight: 600; letter-spacing: -0.022em;
    text-align: center; margin-bottom: 36px;
}
.mm-title { font-size: 28px; line-height: 1.2; font-weight: 600; letter-spacing: -0.02em; }
.mm-section {
    font-size: 13px; font-weight: 500; color: var(--mm-secondary);
    margin: 48px 0 10px;
}
.mm-muted { font-size: 13px; line-height: 1.5; color: var(--mm-secondary); }
.mm-body {
    font-size: 16px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere;
}
.mm-source {
    font-size: 16px; line-height: 1.6; color: var(--mm-secondary); margin-top: 14px;
    white-space: pre-wrap; overflow-wrap: anywhere;
}
.mm-notice { font-size: 13px; color: var(--mm-notice); margin-top: 14px; }
.mm-error { font-size: 13px; color: var(--mm-failed); margin-top: 14px; }
.mm-link {
    font-size: 13px; color: var(--mm-secondary); text-decoration: underline;
    text-decoration-color: var(--mm-hairline); text-underline-offset: 3px;
    overflow-wrap: anywhere;
}
.mm-link:hover { color: var(--mm-ink); text-decoration-color: var(--mm-ink); }
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
.mm-composer .mm-instructions input { font-size: 14px; }
.mm-composer-foot { border-top: 1px solid var(--mm-hairline); padding-top: 8px; margin-top: 4px; }
.mm-field .q-field__control::before, .mm-field .q-field__control::after { display: none; }
.mm-field .q-field__native, .mm-field .q-field__input { color: var(--mm-ink); }
.mm-field ::placeholder { color: var(--mm-tertiary); opacity: 1; }

/* Buttons: one shape, ink on paper. */
.mm-button.q-btn {
    background: var(--mm-ink) !important; color: var(--mm-paper) !important;
    border-radius: 999px; padding: 4px 20px; min-height: 38px;
    font-size: 14px; font-weight: 500; text-transform: none; letter-spacing: 0;
}
.mm-button.q-btn.disabled { opacity: 0.35 !important; }
.mm-icon.q-btn { color: var(--mm-tertiary); }
.mm-icon.q-btn:hover { color: var(--mm-ink); }

/* Rows separated by hairlines, never boxed. */
.mm-ruled > * { border-top: 1px solid var(--mm-hairline); }
.mm-ruled > *:last-child { border-bottom: 1px solid var(--mm-hairline); }
.mm-lead { padding: 6px 0; gap: 8px; align-items: flex-start; flex-wrap: nowrap; width: 100%; }
.mm-lead textarea { font-size: 16px; line-height: 1.5; padding: 8px 0; }
.mm-lead .mm-icon { margin-top: 6px; }
.mm-launch { margin-top: 28px; align-items: center; justify-content: space-between; }
.mm-picker { min-width: 260px; }
.mm-picker .q-field__control { border-radius: 999px; padding: 0 16px; min-height: 38px; }

.mm-thread.q-item { padding: 16px 0; min-height: 0; align-items: flex-start; }
.mm-thread.q-item:hover .mm-thread-text { color: #000; }
.mm-thread .q-focus-helper { display: none; }
.mm-thread-text { font-size: 16px; line-height: 1.5; overflow-wrap: anywhere; }
.mm-thread .q-item__section--side { padding-left: 20px; padding-top: 3px; }

/* Status: a small coloured dot and a quiet word. */
.mm-status {
    font-size: 13px; color: var(--mm-secondary); white-space: nowrap;
    display: inline-flex; align-items: center; gap: 7px;
}
.mm-status::before {
    content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--mm-queued);
}
.mm-status-working::before {
    background: var(--mm-working); animation: mm-pulse 1.4s ease-in-out infinite;
}
.mm-status-finished::before { background: var(--mm-finished); }
.mm-status-failed::before { background: var(--mm-failed); }
@keyframes mm-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }
@media (prefers-reduced-motion: reduce) { .mm-status-working::before { animation: none; } }

/* Evidence: the quotation leads, its source follows. */
.mm-evidence { padding: 18px 0; gap: 8px; align-items: stretch; }
.mm-quote { font-size: 17px; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
.mm-flag { font-size: 12px; color: var(--mm-notice); }
.mm-progress { gap: 4px; margin-top: 20px; }

:focus-visible { outline: 2px solid var(--mm-ink); outline-offset: 2px; border-radius: 4px; }
.q-field :focus-visible { outline: none; }
"""


def apply() -> None:
    """Install the stylesheet and colours for the current page."""
    ui.colors(primary="#1d1d1f", secondary="#6e6e73", accent="#2f6fde", negative="#c9372c")
    ui.add_css(CSS)


def sidebar() -> None:
    with ui.left_drawer(bordered=False).props("width=220").classes("mm-sidebar"):
        ui.label("manyminds").classes("mm-wordmark")
        ui.link("New check", "/").classes("mm-nav")


@contextmanager
def content(*, home: bool = False) -> Iterator[None]:
    """The single centred column every page puts its content in."""
    with ui.column().classes("mm-column" + (" mm-home" if home else "")):
        yield


def status_label(status: ThreadStatus) -> ui.label:
    label = ui.label()
    set_status(label, status)
    return label


def set_status(label: ui.label, status: ThreadStatus) -> None:
    """Change a status label in place, so the row it sits in is not rebuilt."""
    label.set_text(STATUS_TEXT[status])
    label.classes(replace=f"mm-status mm-status-{status.value}")
