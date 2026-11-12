"""The built-in fake model, used by demo mode: deterministic, offline, and clearly labelled."""

import pytest

from manyminds.core.errors import ModelError
from manyminds.core.fake import FakeModelClient
from manyminds.core.models import ErrorKind, JobEventKind, Report, SearchEngine
from manyminds.core.ports import Progress

TEXT = "The bridge opened in 1932 and was the longest in the world."


class SleepRecorder:
    def __init__(self) -> None:
        self.naps: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.naps.append(seconds)


@pytest.fixture
def naps() -> SleepRecorder:
    return SleepRecorder()


@pytest.fixture
def fake(naps: SleepRecorder) -> FakeModelClient:
    return FakeModelClient(sleep=naps)


async def test_decompose_returns_the_requested_number_of_distinct_leads(
    fake: FakeModelClient,
) -> None:
    result = await fake.decompose(TEXT, "", count=10, avoid=[], model="demo/model")

    assert len(result.leads) == 10
    assert len(set(result.leads)) == 10
    assert all(lead.strip() == lead and lead for lead in result.leads)


async def test_decompose_titles_the_check_with_the_start_of_the_text(
    fake: FakeModelClient,
) -> None:
    result = await fake.decompose(TEXT, "", count=3, avoid=[], model="demo/model")

    assert result.title == "Demo: The bridge opened in 1932 and was the…"


async def test_decompose_is_deterministic(fake: FakeModelClient) -> None:
    first = await fake.decompose(TEXT, "", count=5, avoid=[], model="demo/model")
    second = await fake.decompose(TEXT, "", count=5, avoid=[], model="demo/model")

    assert first == second


async def test_decompose_does_not_repeat_leads_it_was_told_to_avoid(
    fake: FakeModelClient,
) -> None:
    first = await fake.decompose(TEXT, "", count=10, avoid=[], model="demo/model")

    more = await fake.decompose(TEXT, "", count=5, avoid=first.leads, model="demo/model")

    assert len(more.leads) == 5
    assert set(more.leads).isdisjoint(first.leads)


async def test_research_returns_a_valid_report_marked_as_demo_content(
    fake: FakeModelClient,
) -> None:
    result = await fake.research(
        "When did the bridge open?",
        TEXT,
        "",
        model="demo/model",
        search=SearchEngine.AUTO,
        on_progress=lambda progress: None,
    )

    report = Report.model_validate(result.report.model_dump())
    assert "When did the bridge open?" in report.summary
    assert report.summary.startswith("Demo report")
    assert len(report.evidence) == 2
    assert {item.stance.value for item in report.evidence} == {"supports", "undermines"}
    assert all(item.url.startswith("https://example.org/demo/") for item in report.evidence)
    assert "demo" in report.undetermined.lower()


async def test_research_reports_progress_as_it_goes(fake: FakeModelClient) -> None:
    seen: list[Progress] = []

    await fake.research(
        "When did the bridge open?",
        TEXT,
        "",
        model="demo/model",
        search=SearchEngine.AUTO,
        on_progress=seen.append,
    )

    assert [progress.kind for progress in seen] == [
        JobEventKind.THINKING,
        JobEventKind.SEARCHING,
        JobEventKind.SOURCES_FOUND,
        JobEventKind.MESSAGE,
        JobEventKind.WRITING,
    ]
    thinking, searching, sources, message, _ = seen
    assert searching.detail == "When did the bridge open?"
    assert thinking.detail.startswith("Demo thinking")
    assert "https://example.org/demo/" in sources.detail
    assert message.detail.startswith("Demo notes")
    # Long enough that a transcript of them has to scroll.
    assert all(len(entry.detail.splitlines()) >= 3 for entry in (thinking, sources, message))


async def test_research_waits_between_steps_without_really_sleeping(
    fake: FakeModelClient, naps: SleepRecorder
) -> None:
    await fake.research(
        "When did the bridge open?",
        TEXT,
        "",
        model="demo/model",
        search=SearchEngine.AUTO,
        on_progress=lambda progress: None,
    )

    assert len(naps.naps) == 3
    assert all(0 < nap <= 5 for nap in naps.naps)


async def research(fake: FakeModelClient, lead: str) -> Report:
    result = await fake.research(
        lead,
        TEXT,
        "",
        model="demo/model",
        search=SearchEngine.AUTO,
        on_progress=lambda progress: None,
    )
    return result.report


async def test_different_leads_take_different_amounts_of_time(
    fake: FakeModelClient, naps: SleepRecorder
) -> None:
    await research(fake, "Lead one")
    first = sum(naps.naps)
    naps.naps.clear()

    await research(fake, "Another lead entirely")

    assert sum(naps.naps) != first


async def test_exactly_one_generated_lead_is_scripted_to_fail(fake: FakeModelClient) -> None:
    leads = (await fake.decompose(TEXT, "", count=10, avoid=[], model="demo/model")).leads
    failing = leads[3]

    with pytest.raises(ModelError) as raised:
        await research(fake, failing)

    assert raised.value.kind is ErrorKind.PROVIDER
    assert raised.value.message == "Demo failure: this lead is scripted to fail."
    for lead in leads[:3] + leads[4:]:
        assert (await research(fake, lead)).summary.startswith("Demo report")
