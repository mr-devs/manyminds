"""The pages. Each one reads from the core and re-reads when the core announces a change."""

import base64
import logging
from collections.abc import Callable

from nicegui import Event, ui
from nicegui.events import (
    ScrollEventArguments,
    UploadEventArguments,
    ValueChangeEventArguments,
)

from manyminds.core.checks import (
    IMAGE_TYPES,
    ChatBusyError,
    NothingToLaunchError,
    TooManyLeadsError,
    check_images,
)
from manyminds.core.events import ChatUpdated, JobUpdated, Update
from manyminds.core.models import (
    ImageFile,
    JobEvent,
    JobEventKind,
    Lead,
    LeadState,
    Message,
    MessageRole,
    MessageStatus,
    Thread,
    ThreadStatus,
)
from manyminds.core.services import Services
from manyminds.core.storage import NotFoundError
from manyminds.ui import theme
from manyminds.ui.follow import Follower
from manyminds.ui.report_view import report_view, usage_line

Updates = Event[Update]

logger = logging.getLogger(__name__)

SEND_KEY = "keydown.enter.exact.prevent"
"""Enter sends; Shift+Enter starts a new line."""
SEND_UNLESS_COMPOSING = "(event) => { if (!event.isComposing && event.keyCode !== 229) emit() }"
"""Runs in the browser. An Enter that only confirms a word being composed, as when typing
Japanese, Chinese or Korean, is not a request to send."""


def _follow(
    updates: Updates,
    anchor: ui.element,
    wanted: Callable[[Update], bool],
    react: Callable[[Update], object],
) -> None:
    """Call react whenever a matching update arrives, for as long as anchor is on the page."""

    def on_update(event: Update) -> None:
        if anchor.is_deleted:
            updates.unsubscribe(on_update)
        elif wanted(event):
            react(event)

    updates.subscribe(on_update)


def _follow_scroll(follower: Follower, classes: str) -> ui.scroll_area:
    """A scrolling area that stays at its end as content arrives, unless the user scrolls up."""

    def on_scroll(event: ScrollEventArguments) -> None:
        # Reported both when the user scrolls and when the content grows.
        if follower.moved(
            position=event.vertical_position,
            size=event.vertical_size,
            container=event.vertical_container_size,
        ):
            area.scroll_to(percent=1.0)

    area = ui.scroll_area(on_scroll=on_scroll).classes(classes)
    return area


def _data_url(media_type: str, data: bytes) -> str:
    """An image as an address the browser can show without fetching anything."""
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


class _ImageTray:
    """Images waiting to go with the next message: picked with the attach button or pasted.

    The browser hands every image, however it arrived, to one hidden uploader, which sends
    it here. File names come from the user's computer and are shown as plain text.
    """

    def __init__(self, problem: Callable[[str], None]) -> None:
        self._waiting: list[tuple[str, ImageFile]] = []
        self._problem = problem
        self._shown = ui.refreshable(self._show)
        self._shown()
        self._uploader = (
            ui.upload(
                on_upload=self._received,
                on_rejected=lambda: problem("That file could not be attached."),
                multiple=True,
                auto_upload=True,
            )
            .props(f'accept="{",".join(IMAGE_TYPES)}"')
            .classes("mm-hidden")
        )
        # Emptied only once every file of a batch has arrived: emptying it sooner would
        # abandon the ones still on their way.
        self._uploader.on("finish", self._uploader.reset)

    def _show(self) -> None:
        if not self._waiting:
            return
        with ui.row().classes("mm-tray"):
            for index, (name, image) in enumerate(self._waiting):
                with ui.row().classes("mm-chip").mark(f"attachment-{index}"):
                    ui.image(_data_url(image.media_type, image.data)).classes("mm-chip-thumb")
                    ui.label(name or "Pasted image").classes("mm-chip-name")
                    (
                        ui.button(icon="close", on_click=lambda index=index: self._remove(index))
                        .props('flat round dense size=xs aria-label="Remove image"')
                        .classes("mm-icon")
                        .mark(f"remove-attachment-{index}")
                    )

    async def _received(self, event: UploadEventArguments) -> None:
        image = ImageFile(event.file.content_type, await event.file.read())
        try:
            check_images([*self.images(), image])
        except ValueError as error:
            self._problem(str(error))
            return
        self._waiting.append((event.file.name, image))
        self._shown.refresh()

    def _remove(self, index: int) -> None:
        del self._waiting[index]
        self._shown.refresh()

    def images(self) -> list[ImageFile]:
        return [image for _, image in self._waiting]

    def take(self) -> list[tuple[str, ImageFile]]:
        """Hand over the waiting images and empty the tray."""
        taken, self._waiting = self._waiting, []
        self._shown.refresh()
        return taken

    def put_back(self, taken: list[tuple[str, ImageFile]]) -> None:
        self._waiting = taken + self._waiting
        self._shown.refresh()

    def attach_button(self) -> None:
        """A button that opens the file picker. It runs in the browser, which only lets a
        page open the picker in direct answer to a click."""
        with (
            ui.button(icon="attach_file")
            .on("click", js_handler=f"() => getElement({self._uploader.id}).$refs.qRef.pickFiles()")
            .props('flat round dense aria-label="Attach an image"')
            .classes("mm-icon")
        ):
            ui.tooltip("Attach an image")

    def take_pasted_images(self, box: ui.textarea) -> None:
        """Send images pasted into the box, such as a screenshot, to the tray. Pasted text
        is left alone."""
        box.on(
            "paste",
            js_handler=(
                "(event) => { const files = Array.from(event.clipboardData?.files || [])"
                ".filter((file) => file.type.startsWith('image/')); if (files.length) {"
                f" event.preventDefault(); getElement({self._uploader.id}).$refs.qRef"
                ".addFiles(files); } }"
            ),
        )


# -- home ---------------------------------------------------------------------------------


def home_page(services: Services, checks_changed: Callable[[], object]) -> None:
    with theme.content(home=True):
        ui.label("What would you like to check?").classes(theme.HEADLINE)
        problem = ui.label().classes(theme.ERROR + " text-center")
        problem.set_visibility(False)

        def show_problem(message: str) -> None:
            problem.set_text(message)
            problem.set_visibility(True)

        with ui.column().classes("mm-composer"):
            tray = _ImageTray(show_problem)
            composer = (
                ui.textarea(
                    placeholder="Paste a claim, a post, a link or a screenshot, and say what "
                    "you want checked"
                )
                .props("borderless autogrow")
                .classes("w-full mm-field")
                .mark("composer")
            )
            tray.take_pasted_images(composer)
            with ui.row().classes("mm-composer-foot items-center no-wrap gap-3"):
                tray.attach_button()
                ui.space()
                button = ui.button("Generate leads").props("unelevated no-caps")
                button.classes(theme.BUTTON)
        problem.move(target_index=-1)
        if services.notice:
            ui.label(services.notice).classes(theme.MUTED + " text-center").mark("notice")

        sent = {"already": False}

        def generate() -> None:
            text = composer.value or ""
            if sent["already"]:
                return  # A second press before the page has changed must not start a second check.
            if not text.strip() and not tray.images():
                show_problem("Paste some text first.")
                return
            try:
                check = services.checks.start_check(text, images=tray.images())
            except ValueError as error:
                show_problem(str(error))
                return
            except Exception as error:
                logger.error("Creating a check failed: %s", type(error).__name__)
                show_problem("Something went wrong and nothing was saved. Please try again.")
                return
            # The leads are worked out in the open, in the conversation itself.
            sent["already"] = True
            checks_changed()
            ui.navigate.to(f"/check/{check.id}")

        button.on_click(generate)
        composer.on(SEND_KEY, generate, js_handler=SEND_UNLESS_COMPOSING)


# -- check --------------------------------------------------------------------------------

LEADS_INTRO = "Leads worth researching. Start any of them, reword them, or leave them."


def confirm_delete(on_confirm: Callable[[], None]) -> ui.dialog:
    with ui.dialog() as dialog, ui.card().classes("mm-dialog"):
        ui.label("Delete this check and its research?").classes("mm-dialog-title")
        ui.label(
            "The conversation, its leads and every report under it are removed from this "
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
    services: Services, updates: Updates, check_id: str, ask_delete: Callable[[str], object]
) -> None:
    """One check as a running conversation: what the user said, the replies, and under each
    reply the leads it put forward, which are started one at a time."""
    store = services.store
    with theme.content(tall=True) as _, ui.column().classes("mm-chat-page") as page:
        try:
            check = store.get_check(check_id)
        except NotFoundError:
            ui.label("This check could not be found.").classes(theme.MUTED)
            return

        with ui.row().classes("mm-head"):
            title = ui.label(check.title).classes("mm-chat-title")
            ui.button("Delete check", on_click=lambda: ask_delete(check_id)).props(
                "flat no-caps"
            ).classes(theme.QUIET)

        def tell(message: str) -> None:
            notice.set_text(message)
            notice.set_visibility(True)

        # Kept outside the parts of the page that are rebuilt.
        chosen = {"model": services.research_models[0]}
        status_labels: dict[str, ui.label] = {}
        groups: dict[str, Callable[[], object]] = {}
        """How to redraw the leads under each reply, by the reply's id."""
        drawn: dict[str, tuple[ui.element, object]] = {}
        """Each message already on the page, and the state it was drawn in."""
        working: dict[str, tuple[ui.element, int]] = {}
        """For each reply still being worked out: where its steps go, and the last one shown."""
        follower = Follower()

        def redraw_leads() -> None:
            for refresh in list(groups.values()):
                refresh()

        def stale() -> None:
            # Another tab changed these leads; show what is really there.
            tell("This list was out of date and has been refreshed.")
            redraw_leads()

        def start(lead_ids: list[str]) -> None:
            """Start research on the given leads with the chosen model."""
            for lead_id in lead_ids:
                try:
                    services.checks.launch_lead(lead_id, [chosen["model"]])
                except NothingToLaunchError:
                    stale()
                    return
                except ValueError as error:
                    tell(str(error))
                    break
                except Exception as error:
                    logger.error("Starting a lead failed: %s", type(error).__name__)
                    tell("Research could not be started. Nothing was changed.")
                    break
            else:
                notice.set_visibility(False)
            redraw_leads()

        def lead_group(message: Message, opening: bool) -> None:
            """The leads listed under one reply. Rebuilt when one is added, removed or started."""

            def add() -> None:
                try:
                    services.checks.add_lead(check_id, message.id)
                except TooManyLeadsError as error:
                    tell(str(error))
                    return
                except Exception as error:
                    logger.error("Adding a lead failed: %s", type(error).__name__)
                    tell("The lead could not be added. Nothing was changed.")
                    return
                notice.set_visibility(False)
                group.refresh()

            def start_all() -> None:
                # Read afresh: the wording may have changed since the list was drawn.
                start(
                    [
                        lead.id
                        for lead in store.list_leads(check_id)
                        if lead.message_id == message.id
                        and lead.state is LeadState.DRAFT
                        and lead.text
                    ]
                )

            @ui.refreshable
            def group() -> None:
                every = store.list_leads(check_id)
                threads = {thread.lead_id: thread for thread in store.list_threads(check_id)}
                drafts = [lead for lead in every if lead.state is LeadState.DRAFT]
                started = [lead for lead in every if lead.state is LeadState.LAUNCHED]
                mine = [lead for lead in every if lead.message_id == message.id]
                if not mine and not opening:
                    return
                if mine and (opening or not message.body):
                    ui.label(LEADS_INTRO).classes("mm-say-note")
                with ui.column().classes("mm-leads").mark("lead-list"):
                    for lead in mine:
                        thread = threads.get(lead.id)
                        if thread is None:
                            _lead_row(
                                services, lead, drafts.index(lead), group.refresh, stale, start
                            )
                        else:
                            status_labels[thread.id] = _started_row(
                                services, thread, started.index(lead)
                            )
                waiting = [lead for lead in mine if lead.id not in threads]
                with ui.row().classes("mm-group-foot"):
                    ui.button("Add a lead", icon="add", on_click=add).props("flat no-caps").classes(
                        "mm-add"
                    )
                    if len(waiting) > 1:
                        ui.button("Research all", on_click=start_all).props("flat no-caps").classes(
                            theme.QUIET
                        ).mark("research-all")

            groups[message.id] = group.refresh
            group()

        def try_again() -> None:
            try:
                services.checks.regenerate(check_id)
            except ValueError:
                pass  # Already under way again, started from another tab.
            except Exception as error:
                logger.error("Generating leads again failed: %s", type(error).__name__)
                tell("That could not be tried again. Nothing was changed.")

        def draw(message: Message, opening: bool) -> None:
            if message.role is MessageRole.USER:
                for image in store.list_attachments(message.id):
                    ui.image(_data_url(image.media_type, image.data)).classes("mm-attached")
                    if image.description:
                        # Shown so the user can see, and correct, how the image was read.
                        ui.label(f"Read as: {image.description}").classes("mm-read-as")
                if message.body:
                    ui.label(message.body).classes("mm-bubble").mark("user-message")
            elif message.status is MessageStatus.PENDING:
                steps = ui.column().classes("mm-steps")
                working[message.id] = (steps, 0)
                with ui.row().classes("mm-pending"):
                    ui.spinner(size="sm", color="grey-6")
                    ui.label(
                        "Working out what to research" if opening else "Writing a reply"
                    ).classes(theme.MUTED)
            elif message.status is MessageStatus.FAILED:
                _steps_taken(services, message)
                reason = message.error_message or "unknown reason"
                lead_in = "Leads could not be generated" if opening else "No reply"
                ui.label(f"{lead_in}: {reason}").classes("mm-reply-error").mark("reply-error")
                if opening:
                    ui.button("Try again", on_click=try_again).props("flat no-caps").classes(
                        theme.QUIET + " self-start"
                    )
            else:
                _steps_taken(services, message, "How these leads were made" if opening else None)
                if message.body and opening:
                    # The opening reply's text is the app's account of what the links showed.
                    with ui.column().classes("mm-read"):
                        ui.label("What was read from your links").classes(theme.LABEL)
                        ui.label(message.body).classes("mm-read-text").mark("read")
                elif message.body:
                    ui.label(message.body).classes("mm-say").mark("reply")
                lead_group(message, opening)

        def show_new_steps(message: Message) -> None:
            """Add the steps taken since the last look, without rebuilding the earlier ones."""
            steps, last = working[message.id]
            with steps:
                for step in store.list_message_steps(message.id, after=last):
                    ui.label(step_text(step.kind, step.detail)).classes("mm-step")
                    last = step.seq
            working[message.id] = (steps, last)

        area = _follow_scroll(follower, "mm-chat")
        with area:
            stream = ui.column().classes("mm-chat-body")

        def sync() -> None:
            """Add messages that are new, and redraw a reply whose state has changed."""
            opening = True
            for message in store.list_messages(check_id):
                is_reply = message.role is MessageRole.ASSISTANT
                known = drawn.get(message.id)
                # A message is redrawn when its status changes or one of its images is read.
                state = (message.status, tuple(store.list_image_descriptions(message.id)))
                if known is None or known[1] != state:
                    slot: ui.element
                    if known is None:
                        with stream:
                            slot = ui.column().classes(f"mm-turn mm-turn-{message.role.value}")
                    else:
                        slot = known[0]
                        slot.clear()
                    working.pop(message.id, None)
                    groups.pop(message.id, None)
                    with slot:
                        draw(message, opening and is_reply)
                    drawn[message.id] = (slot, state)
                if message.id in working:
                    show_new_steps(message)
                if is_reply:
                    opening = False
            if follower.following:
                area.scroll_to(percent=1.0)

        notice = ui.label().classes(theme.NOTICE + " mm-chat-notice")
        notice.set_visibility(False)

        with ui.column().classes("mm-composer mm-chat-composer"):
            tray = _ImageTray(tell)
            composer = (
                ui.textarea(placeholder="Ask about the research, or paste something else to check")
                .props("borderless autogrow rows=1")
                .classes("w-full mm-field")
                .mark("composer")
            )
            tray.take_pasted_images(composer)
            with ui.row().classes("mm-composer-foot items-center no-wrap gap-3"):
                tray.attach_button()
                ui.label("Research with").classes("mm-launch-label")
                (
                    ui.select(
                        list(services.research_models),
                        value=chosen["model"],
                        on_change=lambda event: chosen.update(model=event.value),
                    )
                    .props("borderless dense")
                    .classes("mm-picker")
                    .mark("model-picker")
                )
                ui.space()
                send_button = ui.button("Send").props("unelevated no-caps").classes(theme.BUTTON)

        async def send() -> None:
            text = composer.value or ""
            if not text.strip() and not tray.images():
                tell("Write a message first.")
                return
            notice.set_visibility(False)
            composer.set_value("")
            taken = tray.take()
            # Sending brings the view back to the end, wherever it had been scrolled to.
            follower.following = True

            def give_back(message: str) -> None:
                composer.set_value(text)
                tray.put_back(taken)
                tell(message)

            try:
                await services.checks.send(check_id, text, [image for _, image in taken])
            except ChatBusyError as error:
                give_back(str(error))
            except NotFoundError:
                tell("This check no longer exists.")
            except ValueError as error:
                give_back(str(error))
            except Exception as error:
                logger.error("Sending a message failed: %s", type(error).__name__)
                give_back("The message could not be sent. Nothing was changed.")

        send_button.on_click(send)
        composer.on(SEND_KEY, send, js_handler=SEND_UNLESS_COMPOSING)

        def on_update(event: Update) -> None:
            if isinstance(event, ChatUpdated):
                try:
                    title.set_text(store.get_check(check_id).title)
                except NotFoundError:
                    return  # Deleted from the sidebar or another tab.
                sync()
                return
            label = status_labels.get(event.thread_id)
            if label is None or label.is_deleted:
                # A thread this page has not drawn yet: it was started from another tab.
                redraw_leads()
            else:
                theme.set_status(label, services.checks.thread_status(event.thread_id))

        sync()
        _follow(updates, page, lambda event: event.check_id == check_id, on_update)


def _lead_row(
    services: Services,
    lead: Lead,
    index: int,
    refresh: Callable[[], object],
    stale: Callable[[], None],
    start: Callable[[list[str]], None],
) -> None:
    """A lead that has not been started: reword it, start it, remove it, or leave it."""

    def save(event: ValueChangeEventArguments[str]) -> None:
        # An emptied box is saved as empty; the core refuses to start it until it is refilled.
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
        (
            ui.textarea(value=lead.text, on_change=save, placeholder="Write a lead to research")
            .props("borderless dense autogrow rows=1")
            .classes("grow mm-field")
        )
        (
            ui.button("Go", on_click=lambda: start([lead.id]))
            .props('flat no-caps text-color=white aria-label="Research this lead"')
            .classes("mm-go")
            .mark("go")
        )
        (
            ui.button(icon="close", on_click=remove)
            .props('flat round dense size=sm aria-label="Remove lead"')
            .classes("mm-icon")
            .mark("remove-lead")
        )


def _started_row(services: Services, thread: Thread, index: int) -> ui.label:
    """A lead being researched: its status, and a way into its thread. Returns the status."""
    target = f"/check/{thread.check_id}/thread/{thread.id}"
    with (
        ui.item(on_click=lambda: ui.navigate.to(target))
        .props("clickable")
        .classes("mm-thread")
        .mark(f"thread-row-{index}")
    ):
        with ui.item_section():
            ui.label(thread.lead_text).classes("mm-thread-text")
        with ui.item_section().props("side"):
            status = theme.status_label(services.checks.thread_status(thread.id))
        with ui.item_section().props("side"):
            ui.icon("chevron_right").classes("mm-chevron")
    return status


# -- thread -------------------------------------------------------------------------------

STEP_TEXT = {
    JobEventKind.STARTED: "Started",
    JobEventKind.SEARCHING: "Searching: {detail}",
    JobEventKind.READING: "Reading: {detail}",
    JobEventKind.WRITING: "Writing the report",
    JobEventKind.NOTE: "{detail}",
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


def step_text(kind: JobEventKind, detail: str) -> str:
    """One step as a single line. A step with no fixed wording is shown as it was reported."""
    return STEP_TEXT[kind].format(detail=detail) if kind in STEP_TEXT else detail


def _steps_taken(services: Services, message: Message, heading: str | None = None) -> None:
    """The steps that led to a reply, folded away under a heading, if there were any."""
    steps = services.store.list_message_steps(message.id)
    if not steps:
        return
    with (
        ui.expansion(heading or "Steps taken").props("dense").classes("mm-how"),
        ui.column().classes("mm-steps"),
    ):
        for step in steps:
            ui.label(step_text(step.kind, step.detail)).classes("mm-step")


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


def thread_page(services: Services, updates: Updates, check_id: str, thread_id: str) -> None:
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

        area = _follow_scroll(follower, "mm-transcript")
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
        _follow(
            updates,
            page,
            lambda event: isinstance(event, JobUpdated) and event.thread_id == thread_id,
            lambda _: catch_up(),
        )
