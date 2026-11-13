"""Starting a check: it is saved at once, and the leads arrive in the open, step by step."""

import sqlite3
from pathlib import Path

import pytest

from manyminds.core import storage
from manyminds.core.checks import ChatBusyError, CheckBusyError, CheckService
from manyminds.core.errors import ModelError
from manyminds.core.events import ChatUpdated, EventBus, Update
from manyminds.core.jobs import JobManager
from manyminds.core.models import (
    ErrorKind,
    JobEventKind,
    LeadOrigin,
    MessageRole,
    MessageStatus,
)
from manyminds.core.ports import Progress
from manyminds.core.storage import Store
from support import Faults, RecordingModel, until

TEXT = "The bridge opened in 1932 and was the longest in the world, according to a viral post."


def steps(store: Store, message_id: str) -> list[tuple[JobEventKind, str]]:
    return [(step.kind, step.detail) for step in store.list_message_steps(message_id)]


async def test_a_check_is_saved_at_once_with_its_reply_still_to_come(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.hold_decompose = True

    check = service.start_check(TEXT)

    assert store.get_check(check.id).title == TEXT[:60]
    assert [(m.role, m.status, m.body) for m in store.list_messages(check.id)] == [
        (MessageRole.USER, MessageStatus.COMPLETE, TEXT),
        (MessageRole.ASSISTANT, MessageStatus.PENDING, ""),
    ]
    assert store.list_leads(check.id) == []
    model.release_decompose()
    await jobs.wait_until_idle()


async def test_the_reply_fills_in_with_the_leads_the_title_and_what_was_read(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.title = "Bridge opening claim"
    model.leads = ["Lead A", "Lead B"]
    model.seen = "Opened: A page (https://a.example/p)"

    check = service.start_check(TEXT)
    await jobs.wait_until_idle()

    reply = store.list_messages(check.id)[1]
    assert (reply.status, reply.body) == (MessageStatus.COMPLETE, model.seen)
    assert store.get_check(check.id).title == "Bridge opening claim"
    assert [(lead.text, lead.origin, lead.message_id) for lead in store.list_leads(check.id)] == [
        ("Lead A", LeadOrigin.GENERATED, reply.id),
        ("Lead B", LeadOrigin.GENERATED, reply.id),
    ]
    assert model.decompose_calls[0]["count"] == 5


async def test_each_step_is_saved_under_the_reply_and_announced_as_it_happens(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager, bus: EventBus
) -> None:
    model.steps = [
        Progress(JobEventKind.NOTE, "Opening the links in your message"),
        Progress(JobEventKind.READING, "https://a.example/p"),
    ]
    model.hold_decompose = True
    seen: list[Update] = []
    bus.subscribe(seen.append)

    check = service.start_check(TEXT)
    await until(lambda: len(model.decompose_calls) == 1)

    reply = store.list_messages(check.id)[1]
    assert steps(store, reply.id) == [
        (JobEventKind.NOTE, "Opening the links in your message"),
        (JobEventKind.READING, "https://a.example/p"),
    ]
    assert [step.seq for step in store.list_message_steps(reply.id)] == [1, 2]
    assert [step.seq for step in store.list_message_steps(reply.id, after=1)] == [2]
    assert seen == [ChatUpdated(check_id=check.id)] * 3  # the start, then one for each step
    model.release_decompose()
    await jobs.wait_until_idle()
    assert seen[-1] == ChatUpdated(check_id=check.id)
    assert len(seen) == 4


async def test_a_failure_is_kept_in_the_reply_and_can_be_tried_again(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.decompose_error = ModelError(ErrorKind.RATE_LIMIT, "Too many requests.")
    check = service.start_check(TEXT)
    await jobs.wait_until_idle()

    failed = store.list_messages(check.id)[1]
    assert (failed.status, failed.error_message) == (MessageStatus.FAILED, "Too many requests.")
    assert store.get_check(check.id).source_text == TEXT

    model.decompose_error = None
    service.regenerate(check.id)
    assert store.list_messages(check.id)[1].status is MessageStatus.PENDING
    await jobs.wait_until_idle()

    again = store.list_messages(check.id)[1]
    assert (again.id, again.status, again.error_message) == (
        failed.id,
        MessageStatus.COMPLETE,
        None,
    )
    assert [lead.text for lead in store.list_leads(check.id)] == ["First lead", "Second lead"]


async def test_no_leads_at_all_counts_as_a_failure(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.leads = ["  ", ""]

    check = service.start_check(TEXT)
    await jobs.wait_until_idle()

    reply = store.list_messages(check.id)[1]
    assert reply.status is MessageStatus.FAILED
    assert reply.error_message == "No leads could be generated for this text."


async def test_leads_that_did_not_fail_cannot_be_generated_again(
    service: CheckService, jobs: JobManager
) -> None:
    check = service.start_check(TEXT)
    await jobs.wait_until_idle()

    with pytest.raises(ValueError, match="has not failed"):
        service.regenerate(check.id)


async def test_an_empty_text_starts_nothing(service: CheckService, store: Store) -> None:
    with pytest.raises(ValueError, match="The text to check is empty"):
        service.start_check("  \n ")

    assert store.list_checks() == []


async def test_nothing_else_can_be_done_to_a_check_while_its_leads_are_being_written(
    service: CheckService, model: RecordingModel, jobs: JobManager
) -> None:
    model.hold_decompose = True
    check = service.start_check(TEXT)
    await until(lambda: len(model.decompose_calls) == 1)

    with pytest.raises(ChatBusyError):
        await service.send(check.id, "Hurry up.")
    with pytest.raises(CheckBusyError):
        service.delete_check(check.id)

    model.release_decompose()
    await jobs.wait_until_idle()
    service.delete_check(check.id)


async def test_steps_taken_for_a_later_reply_are_saved_too(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    check = await service.create_check(TEXT)
    model.steps = [Progress(JobEventKind.READING, "https://b.example/q")]

    reply = await service.send(check.id, "And this? https://b.example/q")

    assert steps(store, reply.id) == [(JobEventKind.READING, "https://b.example/q")]


async def test_creating_and_waiting_still_keeps_nothing_when_it_fails(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    model.decompose_error = ModelError(ErrorKind.CREDITS, "Out of credit.")

    with pytest.raises(ModelError, match="Out of credit"):
        await service.create_check(TEXT)

    assert store.list_checks() == []


def test_a_version_three_database_is_upgraded_and_keeps_its_conversations(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    with sqlite3.connect(path) as raw:
        raw.executescript(
            f"BEGIN; {storage.MIGRATIONS[0]} {storage.MIGRATIONS[1]} {storage.MIGRATIONS[2]} "
            "PRAGMA user_version = 3; COMMIT;"
        )
        raw.execute(
            "INSERT INTO checks (id, title, source_text, instructions, created_at, updated_at) "
            "VALUES ('c1', 'T', 'Old text', '', "
            "'2026-11-01T00:00:00+00:00', '2026-11-01T00:00:00+00:00')"
        )
        raw.execute(
            "INSERT INTO messages (id, check_id, seq, role, status, body, created_at) "
            "VALUES ('m1', 'c1', 1, 'user', 'complete', 'Old text', '2026-11-01T00:00:00+00:00')"
        )
    raw.close()

    store = Store(path)

    assert [m.body for m in store.list_messages("c1")] == ["Old text"]
    assert store.list_message_steps("m1") == []
    store.add_message_step("m1", JobEventKind.NOTE, "A step")
    assert steps(store, "m1") == [(JobEventKind.NOTE, "A step")]
    store.close()
    with sqlite3.connect(path) as check:
        assert check.execute("PRAGMA user_version").fetchone() == (6,)


# -- found in code review ------------------------------------------------------------------


async def test_leads_cannot_be_tried_again_while_another_reply_is_being_written(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    import asyncio

    model.decompose_error = ModelError(ErrorKind.RATE_LIMIT, "Too many requests.")
    check = service.start_check(TEXT)
    await jobs.wait_until_idle()
    model.decompose_error = None
    model.hold_reply = True
    sending = asyncio.create_task(service.send(check.id, "Hello?"))
    await until(lambda: len(model.converse_calls) == 1)

    with pytest.raises(ChatBusyError):
        service.regenerate(check.id)
    with pytest.raises(CheckBusyError):
        service.delete_check(check.id)

    model.release_reply()
    await sending
    service.regenerate(check.id)
    await jobs.wait_until_idle()
    assert store.list_messages(check.id)[1].status is MessageStatus.COMPLETE


async def test_a_title_that_cannot_be_saved_leaves_no_hidden_leads_behind(
    service: CheckService, store: Store, jobs: JobManager, faults: Faults
) -> None:
    faults.fail("UPDATE checks SET title")

    check = service.start_check(TEXT)
    await jobs.wait_until_idle()

    assert store.list_messages(check.id)[1].status is MessageStatus.FAILED
    assert store.list_leads(check.id) == []

    service.regenerate(check.id)
    await jobs.wait_until_idle()

    assert [lead.text for lead in store.list_leads(check.id)] == ["First lead", "Second lead"]
