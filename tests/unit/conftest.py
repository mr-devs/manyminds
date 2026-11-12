from collections.abc import Iterator

import pytest

from manyminds.core.checks import CheckService
from manyminds.core.events import EventBus
from manyminds.core.jobs import JobManager
from manyminds.core.models import SearchEngine
from manyminds.core.storage import Store
from support import Faults, RecordingModel, flaky_connection


@pytest.fixture
def faults() -> Faults:
    return Faults()


@pytest.fixture
def store(faults: Faults) -> Iterator[Store]:
    opened = Store(":memory:", connection_factory=flaky_connection(faults))
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
def service(store: Store, model: RecordingModel, jobs: JobManager, bus: EventBus) -> CheckService:
    return CheckService(
        store,
        model,
        jobs,
        bus=bus,
        decompose_model="vendor/fast-model",
        chat_model="vendor/chat-model",
        search_engine=SearchEngine.AUTO,
    )
