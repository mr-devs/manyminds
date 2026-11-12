from collections.abc import Iterator

import pytest

from manyminds.core.checks import CheckService
from manyminds.core.events import EventBus
from manyminds.core.jobs import JobManager
from manyminds.core.models import SearchEngine
from manyminds.core.storage import Store
from support import RecordingModel


@pytest.fixture
def store() -> Iterator[Store]:
    opened = Store(":memory:")
    yield opened
    opened.close()


@pytest.fixture
def model() -> RecordingModel:
    return RecordingModel()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def jobs(store: Store, model: RecordingModel, bus: EventBus) -> JobManager:
    return JobManager(store, model, bus, max_concurrent=2)


@pytest.fixture
def service(store: Store, model: RecordingModel, jobs: JobManager) -> CheckService:
    return CheckService(
        store,
        model,
        jobs,
        decompose_model="vendor/fast-model",
        search_engine=SearchEngine.AUTO,
    )
