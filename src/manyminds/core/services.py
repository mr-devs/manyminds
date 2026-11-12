"""Wires the core together. The interface layer receives one Services object."""

from collections.abc import Sequence
from dataclasses import dataclass

from manyminds.core.checks import CheckService
from manyminds.core.events import EventBus
from manyminds.core.jobs import JobManager
from manyminds.core.models import SearchEngine
from manyminds.core.ports import ModelClient
from manyminds.core.storage import Store


@dataclass(frozen=True)
class Services:
    store: Store
    model: ModelClient
    bus: EventBus
    jobs: JobManager
    checks: CheckService
    research_models: tuple[str, ...]
    """Models offered for research, the default first."""
    notice: str = ""
    """Shown on the home page: where pasted text goes, or that this is a demo."""


def build_services(
    *,
    store: Store,
    model: ModelClient,
    research_models: Sequence[str],
    decompose_model: str,
    search_engine: SearchEngine = SearchEngine.EXA,
    notice: str = "",
    max_concurrent: int = 6,
) -> Services:
    bus = EventBus()
    jobs = JobManager(store, model, bus, max_concurrent=max_concurrent)
    checks = CheckService(
        store, model, jobs, decompose_model=decompose_model, search_engine=search_engine
    )
    return Services(
        store=store,
        model=model,
        bus=bus,
        jobs=jobs,
        checks=checks,
        research_models=tuple(research_models),
        notice=notice,
    )
