"""Leads can be added by hand at any time, up to a limit."""

from __future__ import annotations

import pytest

from manyminds.core.checks import MAX_LEADS, CheckService, TooManyLeadsError
from manyminds.core.models import LeadOrigin, LeadState
from manyminds.core.storage import Store
from support import RecordingModel


async def test_an_added_lead_is_an_empty_draft_at_the_end(
    service: CheckService, store: Store
) -> None:
    check = await service.create_check("Some text.")

    added = service.add_lead(check.id)

    drafts = store.list_draft_leads(check.id)
    assert [lead.text for lead in drafts] == ["First lead", "Second lead", ""]
    assert drafts[-1].id == added.id
    assert (added.origin, added.state) == (LeadOrigin.MANUAL, LeadState.DRAFT)


async def test_a_lead_can_be_added_after_the_others_were_launched(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    check = await service.create_check("Some text.")
    service.launch(check.id, models=["vendor/model-a"])
    await service.jobs.wait_until_idle()

    added = service.add_lead(check.id)
    service.update_lead(added.id, "A lead of my own")
    threads = service.launch(check.id, models=["vendor/model-a"])
    await service.jobs.wait_until_idle()

    assert [thread.lead_text for thread in threads] == ["A lead of my own"]
    assert [t.lead_text for t in store.list_threads(check.id)] == [
        "First lead",
        "Second lead",
        "A lead of my own",
    ]


async def test_the_list_holds_twenty_five_leads_at_most(
    service: CheckService, store: Store
) -> None:
    assert MAX_LEADS == 25
    check = await service.create_check("Some text.")
    for _ in range(23):
        service.add_lead(check.id)

    with pytest.raises(TooManyLeadsError) as caught:
        service.add_lead(check.id)

    assert str(caught.value) == (
        "A list holds 25 leads at most. Research these, then add the rest."
    )
    assert len(store.list_draft_leads(check.id)) == 25


async def test_launched_leads_do_not_count_towards_the_limit(
    service: CheckService, store: Store
) -> None:
    check = await service.create_check("Some text.")
    for _ in range(23):
        service.update_lead(service.add_lead(check.id).id, "Filled in")
    service.launch(check.id, models=["vendor/model-a"])
    await service.jobs.wait_until_idle()

    service.add_lead(check.id)

    assert len(store.list_draft_leads(check.id)) == 1
