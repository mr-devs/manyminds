"""The running conversation on a check: messages, replies, and leads started one at a time."""

import sqlite3
from pathlib import Path

import pytest

from manyminds.core import storage
from manyminds.core.checks import ChatBusyError, CheckService, NothingToLaunchError
from manyminds.core.errors import ModelError
from manyminds.core.events import ChatUpdated, EventBus, Update
from manyminds.core.jobs import JobManager
from manyminds.core.models import (
    ErrorKind,
    JobStatus,
    LeadOrigin,
    LeadState,
    MessageRole,
    MessageStatus,
)
from manyminds.core.ports import ChatContext, LeadNote, PastTurn
from manyminds.core.storage import Store
from support import RecordingModel, report_for, until

TEXT = "The bridge opened in 1932 and was the longest in the world."


def said(store: Store, check_id: str) -> list[tuple[MessageRole, MessageStatus, str]]:
    return [(m.role, m.status, m.body) for m in store.list_messages(check_id)]


# -- the first exchange --------------------------------------------------------------------


async def test_a_new_check_opens_with_the_users_message_and_a_reply_holding_the_leads(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    model.leads = ["Lead A", "Lead B"]

    check = await service.create_check(TEXT)

    assert said(store, check.id) == [
        (MessageRole.USER, MessageStatus.COMPLETE, TEXT),
        (MessageRole.ASSISTANT, MessageStatus.COMPLETE, ""),
    ]
    reply = store.list_messages(check.id)[1]
    assert [(lead.text, lead.message_id) for lead in store.list_leads(check.id)] == [
        ("Lead A", reply.id),
        ("Lead B", reply.id),
    ]


# -- starting leads one at a time ----------------------------------------------------------


async def test_one_lead_can_be_started_and_the_others_are_left_alone(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.leads = ["Lead A", "Lead B", "Lead C"]
    check = await service.create_check(TEXT)
    second = store.list_leads(check.id)[1]

    thread = service.launch_lead(second.id, ["vendor/model-a"])
    await jobs.wait_until_idle()

    assert thread.lead_text == "Lead B"
    assert [t.lead_text for t in store.list_threads(check.id)] == ["Lead B"]
    assert [(job.model, job.status) for job in store.list_jobs(thread.id)] == [
        ("vendor/model-a", JobStatus.DONE)
    ]
    assert [(lead.text, lead.state) for lead in store.list_leads(check.id)] == [
        ("Lead A", LeadState.DRAFT),
        ("Lead B", LeadState.LAUNCHED),
        ("Lead C", LeadState.DRAFT),
    ]
    assert [call["lead"] for call in model.research_calls] == ["Lead B"]


async def test_an_empty_lead_cannot_be_started(service: CheckService, store: Store) -> None:
    check = await service.create_check(TEXT)
    empty = service.add_lead(check.id)

    with pytest.raises(ValueError, match="This lead is empty"):
        service.launch_lead(empty.id, ["vendor/model-a"])

    assert store.list_threads(check.id) == []


async def test_a_lead_cannot_be_started_twice_or_without_a_model(
    service: CheckService, store: Store, jobs: JobManager
) -> None:
    check = await service.create_check(TEXT)
    lead = store.list_leads(check.id)[0]

    with pytest.raises(ValueError, match="Choose at least one model"):
        service.launch_lead(lead.id, [])
    service.launch_lead(lead.id, ["vendor/model-a"])
    with pytest.raises(NothingToLaunchError):
        service.launch_lead(lead.id, ["vendor/model-a"])
    await jobs.wait_until_idle()

    assert len(store.list_threads(check.id)) == 1


async def test_a_lead_added_by_hand_joins_the_reply_it_was_added_under(
    service: CheckService, store: Store
) -> None:
    check = await service.create_check(TEXT)
    reply = store.list_messages(check.id)[1]

    under_reply = service.add_lead(check.id, reply.id)
    unplaced = service.add_lead(check.id)

    assert under_reply.message_id == reply.id
    assert unplaced.message_id == reply.id  # the latest reply, when none is named


# -- sending a message ---------------------------------------------------------------------


async def test_a_message_and_its_reply_are_saved_in_order(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    model.reply = "Two threads agree on the opening year."
    check = await service.create_check(TEXT)

    reply = await service.send(check.id, "  Summarise the findings.  ")

    assert reply.role is MessageRole.ASSISTANT
    assert reply.status is MessageStatus.COMPLETE
    assert said(store, check.id)[2:] == [
        (MessageRole.USER, MessageStatus.COMPLETE, "Summarise the findings."),
        (MessageRole.ASSISTANT, MessageStatus.COMPLETE, "Two threads agree on the opening year."),
    ]
    assert [m.seq for m in store.list_messages(check.id)] == [1, 2, 3, 4]


async def test_the_model_is_given_the_conversation_the_leads_and_only_finished_reports(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.leads = ["Lead A", "Lead B", "Lead C", "Lead D"]
    model.failures = {"Lead B": ModelError(ErrorKind.PROVIDER, "Upstream failed")}
    model.reply = "First answer."
    check = await service.create_check(TEXT)
    leads = store.list_leads(check.id)
    service.launch_lead(leads[0].id, ["vendor/model-a"])
    service.launch_lead(leads[1].id, ["vendor/model-a"])
    await jobs.wait_until_idle()
    model.hold = True
    service.launch_lead(leads[2].id, ["vendor/model-a"])
    await until(lambda: len(model.research_calls) == 3)
    await service.send(check.id, "What do we know?")

    await service.send(check.id, "And what is missing?")

    assert model.converse_calls[1] == {
        "message": "And what is missing?",
        "model": "vendor/chat-model",
        "context": ChatContext(
            turns=(
                PastTurn(MessageRole.USER, TEXT),
                PastTurn(MessageRole.USER, "What do we know?"),
                PastTurn(MessageRole.ASSISTANT, "First answer."),
            ),
            leads=(
                LeadNote("Lead A", "finished", (report_for("Lead A"),)),
                LeadNote("Lead B", "failed"),
                LeadNote("Lead C", "in progress"),
                LeadNote("Lead D", "not started"),
            ),
        ),
    }
    model.release_all()
    await jobs.wait_until_idle()


async def test_leads_proposed_in_a_reply_wait_as_drafts_and_start_nothing(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    model.leads = ["Lead A"]
    model.proposed = ["  lead a ", "Who built the bridge?", "Who built the bridge?", " "]
    check = await service.create_check(TEXT)

    reply = await service.send(check.id, "What else should I look into?")

    assert [
        (lead.text, lead.origin, lead.state, lead.message_id)
        for lead in store.list_leads(check.id)[1:]
    ] == [("Who built the bridge?", LeadOrigin.CONVERSATION, LeadState.DRAFT, reply.id)]
    assert store.list_threads(check.id) == []
    assert model.research_calls == []


async def test_proposed_leads_stop_at_the_limit(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    model.leads = [f"Lead {n}" for n in range(10)]
    check = await service.create_check(TEXT)
    for _ in range(13):
        service.add_lead(check.id)
    model.proposed = ["New one", "New two", "New three"]

    await service.send(check.id, "More?")

    drafts = store.list_draft_leads(check.id)
    assert len(drafts) == 25
    assert [lead.text for lead in drafts[-2:]] == ["New one", "New two"]


async def test_a_failed_reply_is_kept_with_its_reason_and_the_message_stays(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    model.converse_error = ModelError(ErrorKind.RATE_LIMIT, "Too many requests. Try again soon.")
    check = await service.create_check(TEXT)

    reply = await service.send(check.id, "Summarise.")

    assert reply.status is MessageStatus.FAILED
    assert reply.error_message == "Too many requests. Try again soon."
    assert said(store, check.id)[2:] == [
        (MessageRole.USER, MessageStatus.COMPLETE, "Summarise."),
        (MessageRole.ASSISTANT, MessageStatus.FAILED, ""),
    ]


async def test_an_unexpected_failure_is_reported_by_type_only(
    service: CheckService, model: RecordingModel
) -> None:
    model.converse_error = RuntimeError("secret detail that must not be shown")
    check = await service.create_check(TEXT)

    reply = await service.send(check.id, "Summarise.")

    assert reply.status is MessageStatus.FAILED
    assert reply.error_message == "Unexpected error (RuntimeError)"


async def test_an_empty_reply_counts_as_a_failure(
    service: CheckService, model: RecordingModel
) -> None:
    model.reply = "   "
    check = await service.create_check(TEXT)

    reply = await service.send(check.id, "Summarise.")

    assert reply.status is MessageStatus.FAILED
    assert reply.error_message == "The model sent back an empty reply."


async def test_failed_replies_are_left_out_of_what_the_model_is_given(
    service: CheckService, model: RecordingModel
) -> None:
    model.leads = ["Lead A"]
    model.converse_error = ModelError(ErrorKind.PROVIDER, "Upstream failed")
    check = await service.create_check(TEXT)
    await service.send(check.id, "First try.")
    model.converse_error = None

    await service.send(check.id, "Second try.")

    assert model.converse_calls[1]["context"].turns == (
        PastTurn(MessageRole.USER, TEXT),
        PastTurn(MessageRole.USER, "First try."),
    )


async def test_an_empty_message_is_refused_and_nothing_is_saved(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    check = await service.create_check(TEXT)

    with pytest.raises(ValueError, match="Write a message first"):
        await service.send(check.id, "   \n ")

    assert len(store.list_messages(check.id)) == 2
    assert model.converse_calls == []


async def test_a_second_message_waits_for_the_first_reply(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    import asyncio

    model.hold_reply = True
    check = await service.create_check(TEXT)
    first = asyncio.create_task(service.send(check.id, "First."))
    await until(lambda: len(model.converse_calls) == 1)

    assert said(store, check.id)[2:] == [
        (MessageRole.USER, MessageStatus.COMPLETE, "First."),
        (MessageRole.ASSISTANT, MessageStatus.PENDING, ""),
    ]
    with pytest.raises(ChatBusyError, match="Wait for the reply"):
        await service.send(check.id, "Second.")

    model.release_reply()
    await first
    assert len(store.list_messages(check.id)) == 4


async def test_watchers_are_told_when_a_message_is_sent_and_when_the_reply_lands(
    service: CheckService, bus: EventBus
) -> None:
    check = await service.create_check(TEXT)
    seen: list[Update] = []
    bus.subscribe(seen.append)

    await service.send(check.id, "Summarise.")

    assert seen == [ChatUpdated(check_id=check.id), ChatUpdated(check_id=check.id)]


# -- storage -------------------------------------------------------------------------------


async def test_a_reply_cut_off_by_a_restart_is_marked_as_stopped(tmp_path: Path) -> None:
    first = Store(tmp_path / "db.sqlite")
    check = first.create_check_with_leads(
        title="T", source_text=TEXT, instructions="", leads=["Lead A"]
    )
    pending = first.begin_turn(check.id, "Summarise.")
    first.close()

    second = Store(tmp_path / "db.sqlite")

    assert second.fail_pending_messages() == 1
    stopped = second.list_messages(check.id)[-1]
    assert stopped.id == pending.id
    assert stopped.status is MessageStatus.FAILED
    assert stopped.error_message == "Stopped because the app was closed."
    assert second.fail_pending_messages() == 0
    second.close()


async def test_deleting_a_check_removes_its_messages(
    service: CheckService, store: Store, tmp_path: Path
) -> None:
    doomed = await service.create_check(TEXT)
    kept = await service.create_check("Another text.")
    await service.send(doomed.id, "Summarise.")

    service.delete_check(doomed.id)

    assert len(store.list_messages(kept.id)) == 2
    assert store.list_messages(doomed.id) == []


def test_a_version_two_database_gains_a_conversation_for_each_check(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    with sqlite3.connect(path) as raw:
        raw.executescript(
            f"BEGIN; {storage.MIGRATIONS[0]} {storage.MIGRATIONS[1]} "
            "PRAGMA user_version = 2; COMMIT;"
        )
        raw.execute(
            "INSERT INTO checks (id, title, source_text, instructions, created_at, updated_at) "
            "VALUES ('c1', 'T', 'Old text', 'Prefer archives', "
            "'2026-11-01T00:00:00+00:00', '2026-11-01T00:00:00+00:00')"
        )
        raw.execute(
            "INSERT INTO checks (id, title, source_text, instructions, created_at, updated_at) "
            "VALUES ('c2', 'U', 'Other text', '', "
            "'2026-11-02T00:00:00+00:00', '2026-11-02T00:00:00+00:00')"
        )
        for lead_id, check_id, text, position, state in (
            ("l1", "c1", "Lead A", 0, "launched"),
            ("l2", "c1", "Lead B", 1, "draft"),
            ("l3", "c2", "Lead C", 0, "draft"),
        ):
            raw.execute(
                "INSERT INTO leads (id, check_id, text, position, origin, state, created_at) "
                "VALUES (?, ?, ?, ?, 'generated', ?, '2026-11-01T00:00:00+00:00')",
                (lead_id, check_id, text, position, state),
            )
    raw.close()

    store = Store(path)

    assert said(store, "c1") == [
        (MessageRole.USER, MessageStatus.COMPLETE, "Old text\n\nPrefer archives"),
        (MessageRole.ASSISTANT, MessageStatus.COMPLETE, ""),
    ]
    assert said(store, "c2") == [
        (MessageRole.USER, MessageStatus.COMPLETE, "Other text"),
        (MessageRole.ASSISTANT, MessageStatus.COMPLETE, ""),
    ]
    first_reply = store.list_messages("c1")[1]
    other_reply = store.list_messages("c2")[1]
    assert first_reply.id != other_reply.id
    assert [(lead.id, lead.message_id) for lead in store.list_leads("c1")] == [
        ("l1", first_reply.id),
        ("l2", first_reply.id),
    ]
    assert [(lead.id, lead.message_id) for lead in store.list_leads("c2")] == [
        ("l3", other_reply.id)
    ]
    store.close()
