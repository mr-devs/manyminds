from collections.abc import AsyncIterator, Iterator

import pytest
from nicegui.testing import User, user_simulation

from manyminds.core.services import Services, build_services
from manyminds.core.storage import Store
from manyminds.ui.app import build_root
from support import RecordingModel

RESEARCH_MODELS = ["vendor/research-model", "vendor/other-model"]


@pytest.fixture
def model() -> RecordingModel:
    return RecordingModel(title="Bridge claim", leads=["Lead A", "Lead B", "Lead C"])


@pytest.fixture
def services(model: RecordingModel) -> Iterator[Services]:
    store = Store(":memory:")
    yield build_services(
        store=store,
        model=model,
        research_models=RESEARCH_MODELS,
        decompose_model="vendor/fast-model",
        max_concurrent=2,
    )
    store.close()


@pytest.fixture
async def user(services: Services, model: RecordingModel) -> AsyncIterator[User]:
    async with user_simulation(build_root(services)) as simulated:
        yield simulated
    model.release_all()
    await services.jobs.wait_until_idle()
