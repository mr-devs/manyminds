"""The pages. Each one reads from the core and re-reads when the core announces a change."""

from collections.abc import Callable

from nicegui import Event, ui
from nicegui.events import ValueChangeEventArguments

from manyminds.core.errors import ModelError
from manyminds.core.events import JobUpdated
from manyminds.core.models import Job, JobEvent, JobEventKind, JobStatus, Lead
from manyminds.core.services import Services
from manyminds.core.storage import NotFoundError
from manyminds.ui import theme
from manyminds.ui.report_view import report_view

JobUpdates = Event[JobUpdated]


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


def home_page(services: Services) -> None:
    with theme.content():
        ui.label("What would you like to check?").classes(theme.HEADING + " text-center mt-16")
        composer = (
            ui.textarea(placeholder="Paste a claim or a piece of text")
            .props("outlined autogrow rounded input-class=min-h-24")
            .classes("w-full text-base")
            .mark("composer")
        )
        instructions = (
            ui.input(placeholder="Optional instructions, such as specific leads to pursue")
            .props("outlined dense rounded")
            .classes("w-full")
            .mark("instructions")
        )
        problem = ui.label().classes("text-sm text-rose-700")
        problem.set_visibility(False)

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
            else:
                ui.navigate.to(f"/check/{check.id}")
            finally:
                button.enable()
                spinner.set_visibility(False)

        with ui.row().classes("items-center justify-end gap-3"):
            spinner = ui.spinner(size="sm")
            spinner.set_visibility(False)
            button = ui.button("Generate leads", on_click=generate).props("unelevated rounded")


# -- check --------------------------------------------------------------------------------


def check_page(services: Services, updates: JobUpdates, check_id: str) -> None:
    store = services.store
    with theme.content() as _, ui.column().classes("gap-3 items-stretch") as page:
        try:
            check = store.get_check(check_id)
        except NotFoundError:
            ui.label("This check could not be found.").classes(theme.MUTED)
            return

        ui.label(check.title).classes(theme.HEADING)
        ui.label(check.source_text).classes(theme.BODY + " bg-slate-50 rounded-xl p-4")

        status_labels: dict[str, ui.label] = {}

        def update_status(event: JobUpdated) -> None:
            label = status_labels.get(event.thread_id)
            if label is not None:
                theme.set_status(label, services.checks.thread_status(event.thread_id))

        @ui.refreshable
        def threads() -> None:
            # Rebuilt only when the list of threads changes; statuses are updated in place.
            status_labels.clear()
            rows = store.list_threads(check_id)
            if not rows:
                return
            ui.label("Threads").classes(theme.SECTION)
            with ui.list().props("bordered separator").classes("rounded-xl"):
                for index, thread in enumerate(rows):
                    target = f"/check/{check_id}/thread/{thread.id}"
                    with (
                        ui.item(on_click=lambda target=target: ui.navigate.to(target))
                        .props("clickable")
                        .mark(f"thread-row-{index}")
                    ):
                        with ui.item_section():
                            ui.label(thread.lead_text).classes("text-slate-800")
                        with ui.item_section().props("side"):
                            status_labels[thread.id] = theme.status_label(
                                services.checks.thread_status(thread.id)
                            )
                        with ui.item_section().props("side"):
                            started = thread.created_at.astimezone().strftime("%H:%M")
                            ui.label(started).classes(theme.MUTED)

        emptied: set[str] = set()
        """Leads whose box is currently empty; they are not saved until refilled."""

        def stale() -> None:
            # Another tab launched or removed these leads; show what is really there.
            notice.set_text("These leads have already been launched.")
            notice.set_visibility(True)
            lead_editor.refresh()
            threads.refresh()

        @ui.refreshable
        def lead_editor() -> None:
            drafts = store.list_draft_leads(check_id)
            if not drafts:
                return
            ui.label("Leads to research").classes(theme.SECTION)
            for index, lead in enumerate(drafts):
                _lead_row(services, lead, index, emptied, lead_editor.refresh, stale)
            with ui.row().classes("items-center justify-between mt-2"):
                picker = (
                    ui.select(list(services.research_models), value=services.research_models[0])
                    .props("outlined dense rounded")
                    .classes("min-w-64")
                    .mark("model-picker")
                )

                def go() -> None:
                    if emptied & {lead.id for lead in store.list_draft_leads(check_id)}:
                        notice.set_text("A lead is empty. Fill it in or remove it.")
                        notice.set_visibility(True)
                        return
                    try:
                        services.checks.launch(check_id, [picker.value] if picker.value else [])
                    except NotFoundError:
                        stale()
                        return
                    except ValueError as error:
                        notice.set_text(str(error))
                        notice.set_visibility(True)
                        return
                    notice.set_visibility(False)
                    lead_editor.refresh()
                    threads.refresh()

                ui.button("Go", on_click=go).props("unelevated rounded")

        lead_editor()
        notice = ui.label().classes("text-sm text-amber-700")
        notice.set_visibility(False)
        threads()
        _follow(updates, page, lambda event: event.check_id == check_id, update_status)


def _lead_row(
    services: Services,
    lead: Lead,
    index: int,
    emptied: set[str],
    refresh: Callable[[], object],
    stale: Callable[[], None],
) -> None:
    def save(event: ValueChangeEventArguments[str]) -> None:
        if not (event.value or "").strip():
            # Not saved, and Go is refused until the box is refilled or the lead removed.
            emptied.add(lead.id)
            return
        emptied.discard(lead.id)
        try:
            services.checks.update_lead(lead.id, event.value)
        except NotFoundError:
            stale()

    def remove() -> None:
        emptied.discard(lead.id)
        try:
            services.checks.remove_lead(lead.id)
        except NotFoundError:
            stale()
            return
        refresh()

    with ui.row().classes("items-center gap-2 w-full no-wrap").mark(f"lead-row-{index}"):
        ui.input(value=lead.text, on_change=save).props("outlined dense rounded").classes("grow")
        (
            ui.button(icon="close", on_click=remove)
            .props('flat round dense aria-label="Remove lead"')
            .mark("remove-lead")
        )


# -- thread -------------------------------------------------------------------------------

PROGRESS_TEXT = {
    JobEventKind.STARTED: "Started",
    JobEventKind.SEARCHING: "Searching: {detail}",
    JobEventKind.SOURCES_FOUND: "Found {detail}",
    JobEventKind.WRITING: "Writing the report",
    JobEventKind.RETRYING: "Trying again: {detail}",
    JobEventKind.FINISHED: "Report ready",
    JobEventKind.FAILED: "Stopped: {detail}",
}


def _progress_line(event: JobEvent) -> str:
    return PROGRESS_TEXT[event.kind].format(detail=event.detail)


def thread_page(services: Services, updates: JobUpdates, check_id: str, thread_id: str) -> None:
    store = services.store
    with theme.content() as _, ui.column().classes("gap-3 items-stretch") as page:
        try:
            check = store.get_check(check_id)
            thread = store.get_thread(thread_id)
        except NotFoundError:
            ui.label("This thread could not be found.").classes(theme.MUTED)
            return

        ui.link(f"← {check.title}", f"/check/{check_id}").classes(
            "text-sm text-slate-600 no-underline hover:underline"
        )
        ui.label(thread.lead_text).classes(theme.HEADING)

        @ui.refreshable
        def body() -> None:
            theme.status_label(services.checks.thread_status(thread_id))
            for job in store.list_jobs(thread_id):
                _job_view(services, job)

        body()
        _follow(updates, page, lambda event: event.thread_id == thread_id, lambda _: body.refresh())


def _job_view(services: Services, job: Job) -> None:
    store = services.store
    ui.label(job.model).classes(theme.MUTED)
    report = store.get_report(job.id)
    if report is not None:
        report_view(report)
        return
    with ui.column().classes("gap-1"):
        for event in store.list_job_events(job.id):
            ui.label(_progress_line(event)).classes(theme.MUTED)
    if job.status is JobStatus.FAILED and job.error_message:
        ui.label(job.error_message).classes("text-sm text-rose-700")
    elif job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        ui.spinner(type="dots", size="md")
