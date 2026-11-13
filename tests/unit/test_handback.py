"""Research threads hand back to the main conversation, which then writes one report."""

import asyncio

from manyminds.core.checks import CheckService
from manyminds.core.errors import ModelError
from manyminds.core.jobs import JobManager
from manyminds.core.models import (
    ErrorKind,
    LeadOrigin,
    MessageKind,
    MessageRole,
    MessageStatus,
    Report,
)
from manyminds.core.ports import LeadNote, PastTurn
from manyminds.core.storage import Store
from support import RecordingModel, report_for, until

TEXT = "The bridge opened in 1932 and was the longest in the world."
MODELS = ["vendor/model-a"]


def kinds(store: Store, check_id: str) -> list[tuple[MessageKind, MessageStatus]]:
    return [(m.kind, m.status) for m in store.list_messages(check_id)][2:]


async def started(service: CheckService, store: Store, *leads: int) -> str:
    check = await service.create_check(TEXT)
    every = store.list_leads(check.id)
    for index in leads:
        service.launch_lead(every[index].id, MODELS)
    return check.id


async def test_each_thread_hands_back_as_it_finishes_and_then_the_report_is_written(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.leads = ["Lead A", "Lead B", "Lead C"]
    model.final_report = "## What was found\n\nBoth leads agree."
    model.hold = True
    check_id = await started(service, store, 0, 1)
    await until(lambda: len(model.research_calls) == 2)

    model.release("Lead B")
    await until(lambda: len(kinds(store, check_id)) == 1)
    assert kinds(store, check_id) == [(MessageKind.HANDBACK, MessageStatus.COMPLETE)]
    assert model.report_calls == []  # Lead A is still being researched

    model.release("Lead A")
    await jobs.wait_until_idle()

    messages = store.list_messages(check_id)[2:]
    assert [(m.kind, m.status) for m in messages] == [
        (MessageKind.HANDBACK, MessageStatus.COMPLETE),
        (MessageKind.HANDBACK, MessageStatus.COMPLETE),
        (MessageKind.REPORT, MessageStatus.COMPLETE),
    ]
    handed_back = [
        store.get_thread(store.get_job(m.job_id or "").thread_id).lead_text for m in messages[:2]
    ]
    assert handed_back == ["Lead B", "Lead A"]
    assert messages[2].role is MessageRole.ASSISTANT
    assert messages[2].body == "## What was found\n\nBoth leads agree."
    assert len(model.report_calls) == 1


async def test_the_report_is_written_from_what_every_thread_handed_back(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.leads = ["Lead A", "Lead B", "Lead C"]
    model.reports = {"Lead A": Report(notes="A's notes.", unreturned_links=["https://x.example/a"])}
    model.failures = {"Lead B": ModelError(ErrorKind.PROVIDER, "Upstream failed")}
    check_id = await started(service, store, 0, 1)

    await jobs.wait_until_idle()

    (call,) = model.report_calls
    assert call["model"] == "vendor/chat-model"
    assert call["context"].turns == (PastTurn(MessageRole.USER, TEXT),)
    assert call["context"].leads == (
        LeadNote(
            "Lead A",
            "finished",
            (Report(notes="A's notes.", unreturned_links=["https://x.example/a"]),),
        ),
        LeadNote("Lead B", "failed"),
        LeadNote("Lead C", "not started"),
    )
    assert kinds(store, check_id)[-1] == (MessageKind.REPORT, MessageStatus.COMPLETE)


async def test_no_report_is_written_when_every_lead_failed(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.leads = ["Lead A"]
    model.failures = {"Lead A": ModelError(ErrorKind.PROVIDER, "Upstream failed")}
    check_id = await started(service, store, 0)

    await jobs.wait_until_idle()

    assert kinds(store, check_id) == [(MessageKind.HANDBACK, MessageStatus.COMPLETE)]
    assert model.report_calls == []


async def test_leads_started_later_get_a_report_of_their_own_covering_everything(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.leads = ["Lead A", "Lead B"]
    check_id = await started(service, store, 0)
    await jobs.wait_until_idle()

    service.launch_lead(store.list_leads(check_id)[1].id, MODELS)
    await jobs.wait_until_idle()

    assert [kind for kind, _ in kinds(store, check_id)] == [
        MessageKind.HANDBACK,
        MessageKind.REPORT,
        MessageKind.HANDBACK,
        MessageKind.REPORT,
    ]
    assert model.report_calls[1]["context"].leads == (
        LeadNote("Lead A", "finished", (report_for("Lead A"),)),
        LeadNote("Lead B", "finished", (report_for("Lead B"),)),
    )
    assert PastTurn(MessageRole.ASSISTANT, "The report.") in model.report_calls[1]["context"].turns


async def test_research_that_ends_during_a_reply_is_reported_once_the_reply_lands(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.leads = ["Lead A"]
    model.hold = True
    model.hold_reply = True
    check_id = await started(service, store, 0)
    await until(lambda: len(model.research_calls) == 1)
    sending = asyncio.create_task(service.send(check_id, "How is it going?"))
    await until(lambda: len(model.converse_calls) == 1)

    model.release("Lead A")
    await until(lambda: (MessageKind.HANDBACK, MessageStatus.COMPLETE) in kinds(store, check_id))
    assert model.report_calls == []

    model.release_reply()
    await sending
    await jobs.wait_until_idle()

    assert [kind for kind, _ in kinds(store, check_id)] == [
        MessageKind.REPLY,  # what the user said
        MessageKind.REPLY,  # the reply to it
        MessageKind.HANDBACK,
        MessageKind.REPORT,
    ]
    assert len(model.report_calls) == 1


async def test_leads_the_report_proposes_wait_as_drafts(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.leads = ["Lead A"]
    model.report_leads = ["Who built the bridge?", "lead a"]
    check_id = await started(service, store, 0)

    await jobs.wait_until_idle()

    report = store.list_messages(check_id)[-1]
    proposed = store.list_leads(check_id)[1:]
    assert [(lead.text, lead.origin, lead.message_id) for lead in proposed] == [
        ("Who built the bridge?", LeadOrigin.CONVERSATION, report.id)
    ]
    assert len(store.list_threads(check_id)) == 1


async def test_a_report_that_cannot_be_written_says_why_and_nothing_is_stuck(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.leads = ["Lead A"]
    model.report_error = ModelError(ErrorKind.RATE_LIMIT, "Too many requests.")
    check_id = await started(service, store, 0)

    await jobs.wait_until_idle()

    failed = store.list_messages(check_id)[-1]
    assert (failed.kind, failed.status, failed.error_message) == (
        MessageKind.REPORT,
        MessageStatus.FAILED,
        "Too many requests.",
    )
    reply = await service.send(check_id, "Summarise instead.")
    assert reply.status is MessageStatus.COMPLETE


async def test_hand_backs_are_not_replayed_to_the_model_as_things_said(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.leads = ["Lead A"]
    check_id = await started(service, store, 0)
    await jobs.wait_until_idle()

    await service.send(check_id, "Thanks.")

    assert model.converse_calls[0]["context"].turns == (
        PastTurn(MessageRole.USER, TEXT),
        PastTurn(MessageRole.ASSISTANT, "The report."),
    )


async def test_a_lead_added_by_hand_goes_under_a_reply_not_a_hand_back(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.leads = ["Lead A"]
    model.report_error = ModelError(ErrorKind.RATE_LIMIT, "Too many requests.")
    check_id = await started(service, store, 0)
    await jobs.wait_until_idle()

    added = service.add_lead(check_id)

    assert added.message_id == store.list_messages(check_id)[1].id
