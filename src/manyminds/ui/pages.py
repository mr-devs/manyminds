"""The pages. Each one reads from the core and re-reads when the core announces a change."""

import logging
from collections.abc import Callable

from nicegui import Event, ui
from nicegui.events import ScrollEventArguments, ValueChangeEventArguments

from manyminds.core.checks import CheckBusyError, NothingToLaunchError, TooManyLeadsError
from manyminds.core.errors import ModelError
from manyminds.core.events import JobUpdated
from manyminds.core.models import JobEvent, JobEventKind, Lead, ThreadStatus
from manyminds.core.services import Services
from manyminds.core.storage import NotFoundError
from manyminds.ui import theme
from manyminds.ui.follow import Follower
from manyminds.ui.report_view import report_view, usage_line

JobUpdates = Event[JobUpdated]

logger = logging.getLogger(__name__)


def _follow(
    updates: JobUpdates,
    anchor: ui.element,
    wanted: Callable[[JobUpdated], bool],
    react: Callable[[JobUpdated], object],
) -> None:
    """Call react whenever a matching job changes, for as long as anchor is on the page."""

    def on_update(event: JobUpdated) -> None:
        if anchor.is_deleted:
            updates.unsubscribe(on_update)
        elif wanted(event):
            react(event)

    updates.subscribe(on_update)


# -- home ---------------------------------------------------------------------------------


def home_page(services: Services, checks_changed: Callable[[], object]) -> None:
    with theme.content(home=True):
        ui.label("What would you like to check?").classes(theme.HEADLINE)
        with ui.column().classes("mm-composer"):
            composer = (
                ui.textarea(placeholder="Paste a claim or a piece of text")
                .props("borderless autogrow")
                .classes("w-full mm-field")
                .mark("composer")
            )
            with ui.row().classes("mm-composer-foot items-center no-wrap gap-3"):
                instructions = (
                    ui.input(placeholder="Add instructions, such as leads to pursue (optional)")
                    .props("borderless dense")
                    .classes("grow mm-field mm-instructions")
                    .mark("instructions")
                )
                spinner = ui.spinner(size="sm", color="grey-6")
                spinner.set_visibility(False)
                button = ui.button("Generate leads").props("unelevated no-caps")
                button.classes(theme.BUTTON)
        problem = ui.label().classes(theme.ERROR + " text-center")
        problem.set_visibility(False)
        if services.notice:
            ui.label(services.notice).classes(theme.MUTED + " text-center").mark("notice")

        def show_problem(message: str) -> None:
            problem.set_text(message)
            problem.set_visibility(True)

        async def generate() -> None:
            text = composer.value or ""
            if not text.strip():
                show_problem("Paste some text first.")
                return
            problem.set_visibility(False)
            button.disable()
            spinner.set_visibility(True)
            try:
                check = await services.checks.create_check(text, instructions.value or "")
            except ModelError as error:
                show_problem(error.message)
            except Exception as error:
                logger.error("Creating a check failed: %s", type(error).__name__)
                show_problem("Something went wrong and nothing was saved. Please try again.")
            else:
                checks_changed()
                ui.navigate.to(f"/check/{check.id}")
            finally:
                button.enable()
                spinner.set_visibility(False)

        button.on_click(generate)


# -- check --------------------------------------------------------------------------------


def _confirm_delete(on_confirm: Callable[[], None]) -> ui.dialog:
    with ui.dialog() as dialog, ui.card().classes("mm-dialog"):
        ui.label("Delete this check and its research?").classes("mm-dialog-title")
        ui.label(
            "The pasted text, its leads and every report under it are removed from this "
            "computer. This cannot be undone."
        ).classes(theme.MUTED)
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps").classes(theme.QUIET)

            def confirmed() -> None:
                dialog.close()
                on_confirm()

            ui.button("Delete", on_click=confirmed).props("flat no-caps").classes(
                theme.BUTTON + " mm-danger"
            ).mark("confirm-delete")
    return dialog


def check_page(
    services: Services, updates: JobUpdates, check_id: str, checks_changed: Callable[[], object]
) -> None:
    store = services.store
    with theme.content() as _, ui.column().classes("gap-0 items-stretch") as page:
        try:
            check = store.get_check(check_id)
        except NotFoundError:
            ui.label("This check could not be found.").classes(theme.MUTED)
            return

        def delete() -> None:
            try:
                services.checks.delete_check(check_id)
            except NotFoundError:
                pass  # Already deleted from another tab; the outcome is the same.
            except CheckBusyError as error:
                tell(str(error))
                return
            except Exception as error:
                logger.error("Deleting a check failed: %s", type(error).__name__)
                tell("This check could not be deleted. Nothing was changed.")
                return
            checks_changed()
            ui.navigate.to("/")

        dialog = _confirm_delete(delete)
        with ui.row().classes("mm-head"):
            ui.label(check.title).classes(theme.TITLE)
            ui.button("Delete check", on_click=dialog.open).props("flat no-caps").classes(
                theme.QUIET
            )
        with ui.column().classes(theme.PANEL):
            ui.label("Text being checked").classes(theme.LABEL)
            ui.label(check.source_text).classes(theme.SOURCE)

        status_labels: dict[str, ui.label] = {}

        def update_status(event: JobUpdated) -> None:
            label = status_labels.get(event.thread_id)
            if label is None:
                # A thread this page has not drawn yet: it was launched from another tab.
                redraw()
            else:
                theme.set_status(label, services.checks.thread_status(event.thread_id))

        @ui.refreshable
        def threads() -> None:
            # Rebuilt only when the list of threads changes; statuses are updated in place.
            status_labels.clear()
            rows = store.list_threads(check_id)
            if not rows:
                return
            ui.label("Threads").classes(theme.SECTION)
            ui.label("One for each lead being researched. Open one to follow its work.").classes(
                "mm-section-note"
            )
            with ui.list().classes("mm-threads"):
                for index, thread in enumerate(rows):
                    target = f"/check/{check_id}/thread/{thread.id}"
                    with (
                        ui.item(on_click=lambda target=target: ui.navigate.to(target))
                        .props("clickable")
                        .classes("mm-thread")
                        .mark(f"thread-row-{index}")
                    ):
                        with ui.item_section():
                            ui.label(thread.lead_text).classes("mm-thread-text")
                        with ui.item_section().props("side"):
                            status_labels[thread.id] = theme.status_label(
                                services.checks.thread_status(thread.id)
                            )
                        with ui.item_section().props("side"):
                            started = theme.format_when(thread.created_at.astimezone())
                            ui.label(started).classes(theme.MUTED)

        def tell(message: str) -> None:
            notice.set_text(message)
            notice.set_visibility(True)

        def redraw() -> None:
            lead_editor.refresh()
            threads.refresh()

        def stale() -> None:
            # Another tab changed these leads; show what is really there.
            tell("This list was out of date and has been refreshed.")
            redraw()

        # Kept outside the editor, which is rebuilt whenever a lead is added or removed.
        chosen = {"model": services.research_models[0]}

        def add_lead() -> None:
            try:
                services.checks.add_lead(check_id)
            except TooManyLeadsError as error:
                tell(str(error))
                return
            except Exception as error:
                logger.error("Adding a lead failed: %s", type(error).__name__)
                tell("The lead could not be added. Nothing was changed.")
                return
            notice.set_visibility(False)
            lead_editor.refresh()

        @ui.refreshable
        def lead_editor() -> None:
            drafts = store.list_draft_leads(check_id)
            if drafts:
                ui.label("Leads to research").classes(theme.SECTION)
                ui.label("Edit any lead, remove it, or add your own before starting.").classes(
                    "mm-section-note"
                )
                with ui.column().classes("mm-leads").mark("lead-list"):
                    for index, lead in enumerate(drafts):
                        _lead_row(services, lead, index, lead_editor.refresh, stale)
            ui.button("Add a lead", icon="add", on_click=add_lead).props("flat no-caps").classes(
                "mm-add" if drafts else "mm-add mm-add-alone"
            )
            if not drafts:
                return
            with ui.row().classes("mm-launch"):
                ui.label("Research with").classes("mm-launch-label")
                picker = (
                    ui.select(
                        list(services.research_models),
                        value=chosen["model"],
                        on_change=lambda event: chosen.update(model=event.value),
                    )
                    .props("outlined dense")
                    .classes("mm-picker")
                    .mark("model-picker")
                )

                def go() -> None:
                    try:
                        services.checks.launch(check_id, [picker.value] if picker.value else [])
                    except NothingToLaunchError:
                        stale()
                        return
                    except ValueError as error:
                        tell(str(error))
                        return
                    except Exception as error:
                        logger.error("Launch failed: %s", type(error).__name__)
                        tell("Research could not be started. Nothing was changed.")
                        return
                    notice.set_visibility(False)
                    redraw()

                ui.button("Go", on_click=go).props("unelevated no-caps").classes(theme.BUTTON)

        lead_editor()
        notice = ui.label().classes(theme.NOTICE)
        notice.set_visibility(False)
        threads()
        _follow(updates, page, lambda event: event.check_id == check_id, update_status)


def _lead_row(
    services: Services,
    lead: Lead,
    index: int,
    refresh: Callable[[], object],
    stale: Callable[[], None],
) -> None:
    def save(event: ValueChangeEventArguments[str]) -> None:
        # An emptied box is saved as empty; the core refuses to launch it until it is refilled.
        try:
            services.checks.update_lead(lead.id, event.value or "")
        except NotFoundError:
            stale()

    def remove() -> None:
        try:
            services.checks.remove_lead(lead.id)
        except NotFoundError:
            stale()
            return
        refresh()

    with ui.row().classes("mm-lead").mark(f"lead-row-{index}"):
        ui.label(str(index + 1)).classes("mm-lead-number")
        (
            ui.textarea(value=lead.text, on_change=save, placeholder="Write a lead to research")
            .props("borderless dense autogrow rows=1")
            .classes("grow mm-field")
        )
        (
            ui.button(icon="close", on_click=remove)
            .props('flat round dense size=sm aria-label="Remove lead"')
            .classes("mm-icon")
            .mark("remove-lead")
        )


# -- thread -------------------------------------------------------------------------------

STEP_TEXT = {
    JobEventKind.STARTED: "Started",
    JobEventKind.SEARCHING: "Searching: {detail}",
    JobEventKind.WRITING: "Writing the report",
    JobEventKind.RETRYING: "Trying again: {detail}",
    JobEventKind.FINISHED: "Report ready",
    JobEventKind.FAILED: "Stopped: {detail}",
}
"""Entries shown as a single quiet line."""

PASSAGE_HEADING = {
    JobEventKind.THINKING: "Thinking",
    JobEventKind.SOURCES_FOUND: "Sources found",
    JobEventKind.MESSAGE: None,
}
"""Entries shown as a passage of the model's or the search tool's own text."""


def _transcript_entry(event: JobEvent) -> None:
    """Add one transcript entry. Text from a model or a web page is shown as plain text."""
    if event.kind in STEP_TEXT:
        text = STEP_TEXT[event.kind].format(detail=event.detail)
        ui.label(text).classes("mm-step").mark("transcript-text")
        return
    with ui.column().classes(f"mm-passage mm-passage-{event.kind.value}"):
        heading = PASSAGE_HEADING[event.kind]
        if heading:
            ui.label(heading).classes("mm-passage-heading")
        ui.label(event.detail).classes("mm-passage-text").mark("transcript-text")


def thread_page(services: Services, updates: JobUpdates, check_id: str, thread_id: str) -> None:
    store = services.store
    with theme.content(tall=True) as _, ui.column().classes("mm-thread-page") as page:
        try:
            check = store.get_check(check_id)
            thread = store.get_thread(thread_id)
        except NotFoundError:
            ui.label("This thread could not be found.").classes(theme.MUTED)
            return

        ui.link(f"← {check.title}", f"/check/{check_id}").classes("mm-back")
        ui.label(thread.lead_text).classes(theme.TITLE)

        def try_again() -> None:
            try:
                services.checks.retry_thread(thread_id)
            except ValueError:
                pass  # It is already running again, started from another tab.
            except Exception as error:
                logger.error("Trying a thread again failed: %s", type(error).__name__)
                return
            catch_up()

        with ui.row().classes("items-center gap-3 mt-3"):
            status = theme.status_label(services.checks.thread_status(thread_id))
            for model in dict.fromkeys(job.model for job in store.list_jobs(thread_id)):
                ui.label(model).classes(theme.MUTED)
            again = ui.button("Try again", on_click=try_again).props("flat no-caps")
            again.classes(theme.QUIET)

        shown: dict[str, int] = {}
        """The number of the last transcript entry of each job already on the page."""
        concluded: set[str] = set()
        """Jobs whose report is already on the page."""
        follower = Follower()

        def on_scroll(event: ScrollEventArguments) -> None:
            # Reported both when the user scrolls and when the transcript grows.
            if follower.moved(
                position=event.vertical_position,
                size=event.vertical_size,
                container=event.vertical_container_size,
            ):
                area.scroll_to(percent=1.0)

        area = ui.scroll_area(on_scroll=on_scroll).classes("mm-transcript")
        with area:
            transcript = ui.column().classes("mm-transcript-body")

        def catch_up() -> None:
            """Append whatever is new. Earlier entries are never rebuilt."""
            with transcript:
                for job in store.list_jobs(thread_id):
                    for event in store.list_job_events(job.id, after=shown.get(job.id, 0)):
                        _transcript_entry(event)
                        shown[job.id] = event.seq
                    report = store.get_report(job.id)
                    if report is not None and job.id not in concluded:
                        concluded.add(job.id)
                        with ui.column().classes("mm-report"):
                            report_view(report)
                            used = usage_line(job.usage)
                            if used:
                                ui.label(used).classes(theme.MUTED + " mm-usage").mark("usage")
            current = services.checks.thread_status(thread_id)
            theme.set_status(status, current)
            again.set_visibility(current is ThreadStatus.FAILED)
            if follower.following:
                area.scroll_to(percent=1.0)

        catch_up()
        _follow(updates, page, lambda event: event.thread_id == thread_id, lambda _: catch_up())
