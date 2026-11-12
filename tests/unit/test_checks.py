"""Starting a check: generating leads, editing them, and launching research."""

import pytest

from manyminds.core.checks import CheckService
from manyminds.core.errors import ModelError
from manyminds.core.models import (
    ErrorKind,
    JobStatus,
    LeadOrigin,
    LeadState,
    SearchEngine,
)
from manyminds.core.storage import Store
from support import RecordingModel

TEXT = "The bridge opened in 1932 and was the longest in the world."


async def test_creating_a_check_stores_the_text_and_generated_leads(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    model.title = "Bridge opening claim"
    model.leads = ["When did the bridge open?", "Was it the longest in the world?"]

    check = await service.create_check(TEXT, "Prefer archives")

    assert store.get_check(check.id) == check
    assert check.title == "Bridge opening claim"
    assert check.source_text == TEXT
    assert check.instructions == "Prefer archives"
    leads = store.list_draft_leads(check.id)
    assert [lead.text for lead in leads] == [
        "When did the bridge open?",
        "Was it the longest in the world?",
    ]
    assert all(lead.origin is LeadOrigin.GENERATED for lead in leads)
    assert all(lead.state is LeadState.DRAFT for lead in leads)


async def test_lead_generation_asks_the_fast_model_for_ten_leads(
    service: CheckService, model: RecordingModel
) -> None:
    await service.create_check(TEXT, "Prefer archives")

    assert model.decompose_calls == [
        {
            "text": TEXT,
            "instructions": "Prefer archives",
            "count": 10,
            "avoid": [],
            "model": "vendor/fast-model",
        }
    ]


async def test_at_most_ten_generated_leads_are_kept(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    model.leads = [f"Lead number {n}" for n in range(1, 15)]

    check = await service.create_check(TEXT)

    assert [lead.text for lead in store.list_draft_leads(check.id)] == [
        "Lead number 1",
        "Lead number 2",
        "Lead number 3",
        "Lead number 4",
        "Lead number 5",
        "Lead number 6",
        "Lead number 7",
        "Lead number 8",
        "Lead number 9",
        "Lead number 10",
    ]


async def test_blank_and_duplicate_leads_are_dropped(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    model.leads = [
        "  When did it open?  ",
        "",
        "   ",
        "when did it   open?",
        "Who built it?",
        "WHO BUILT IT?",
    ]

    check = await service.create_check(TEXT)

    assert [lead.text for lead in store.list_draft_leads(check.id)] == [
        "When did it open?",
        "Who built it?",
    ]


@pytest.mark.parametrize("blank_title", ["", "   "])
async def test_missing_title_falls_back_to_the_start_of_the_text(
    service: CheckService, model: RecordingModel, blank_title: str
) -> None:
    model.title = blank_title
    long_text = "Line one of the claim\ncontinues on a second line " + "x" * 100

    check = await service.create_check(long_text)

    assert check.title == "Line one of the claim continues on a second line xxxxxxxxxxx"
    assert len(check.title) == 60


@pytest.mark.parametrize("blank", ["", "   \n\t"])
async def test_blank_text_is_refused_without_calling_the_model(
    service: CheckService, store: Store, model: RecordingModel, blank: str
) -> None:
    with pytest.raises(ValueError, match="text"):
        await service.create_check(blank)

    assert model.decompose_calls == []
    assert store.list_checks() == []


async def test_failed_lead_generation_creates_no_check(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    model.decompose_error = ModelError(ErrorKind.RATE_LIMIT, "Too many requests")

    with pytest.raises(ModelError) as raised:
        await service.create_check(TEXT)

    assert raised.value.kind is ErrorKind.RATE_LIMIT
    assert store.list_checks() == []


async def test_launch_creates_one_queued_job_per_lead(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    model.leads = ["Lead A", "Lead B", "Lead C"]
    model.hold = True
    check = await service.create_check(TEXT, "Prefer archives")

    threads = service.launch(check.id, ["vendor/research-model"])

    assert [thread.lead_text for thread in threads] == ["Lead A", "Lead B", "Lead C"]
    assert store.list_threads(check.id) == threads
    assert store.list_draft_leads(check.id) == []
    for thread in threads:
        (job,) = store.list_jobs(thread.id)
        assert job.status is JobStatus.QUEUED
        assert job.model == "vendor/research-model"
        assert job.search_engine is SearchEngine.AUTO
        assert job.instructions == "Prefer archives"
    model.release_all()
    await service.jobs.wait_until_idle()


async def test_launch_uses_the_edited_list(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    model.leads = ["Keep me", "Remove me", "Edit me"]
    check = await service.create_check(TEXT)
    _keep, remove, edit = store.list_draft_leads(check.id)

    service.remove_lead(remove.id)
    service.update_lead(edit.id, "  Edited lead  ")
    threads = service.launch(check.id, ["vendor/research-model"])
    await service.jobs.wait_until_idle()

    assert [thread.lead_text for thread in threads] == ["Keep me", "Edited lead"]
    assert [call["lead"] for call in model.research_calls] == ["Keep me", "Edited lead"]


async def test_launch_is_refused_while_a_lead_is_empty(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    check = await service.create_check(TEXT)
    first, second = store.list_draft_leads(check.id)

    service.update_lead(second.id, "   ")

    assert [lead.text for lead in store.list_draft_leads(check.id)] == [first.text, ""]
    with pytest.raises(ValueError, match=r"A lead is empty\. Fill it in or remove it\."):
        service.launch(check.id, ["vendor/research-model"])
    assert store.list_threads(check.id) == []
    assert len(store.list_draft_leads(check.id)) == 2
    assert model.research_calls == []


async def test_launch_needs_a_model(service: CheckService, store: Store) -> None:
    check = await service.create_check(TEXT)

    with pytest.raises(ValueError, match="model"):
        service.launch(check.id, [])

    assert store.list_threads(check.id) == []


async def test_launch_needs_a_lead(service: CheckService, store: Store) -> None:
    check = await service.create_check(TEXT)
    for lead in store.list_draft_leads(check.id):
        service.remove_lead(lead.id)

    with pytest.raises(ValueError, match="lead"):
        service.launch(check.id, ["vendor/research-model"])

    assert store.list_threads(check.id) == []
