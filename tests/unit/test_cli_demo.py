"""`manyminds --demo` runs the whole app on the built-in fake model, leaving nothing behind."""

from pathlib import Path
from typing import Any

import pytest

from manyminds import cli
from manyminds.core.fake import FakeModelClient
from manyminds.core.services import Services


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Capture what the command would serve instead of starting a server."""
    captured: dict[str, Any] = {}

    def fake_run(services: Services, **options: Any) -> None:
        captured["services"] = services
        captured.update(options)

    monkeypatch.setattr("manyminds.ui.app.run", fake_run)
    monkeypatch.setenv("MANYMINDS_DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return captured


def test_demo_serves_the_app_on_the_fake_model(served: dict[str, Any]) -> None:
    status = cli.main(["--demo"])

    assert status == 0
    assert isinstance(served["services"].model, FakeModelClient)
    assert served["services"].research_models == ("demo/model",)


def test_demo_opens_the_browser_on_a_free_port_by_default(served: dict[str, Any]) -> None:
    cli.main(["--demo"])

    assert served["port"] is None
    assert served["show"] is True


def test_demo_accepts_a_port_and_can_leave_the_browser_closed(served: dict[str, Any]) -> None:
    cli.main(["--demo", "--port", "8123", "--no-browser"])

    assert served["port"] == 8123
    assert served["show"] is False


def test_demo_says_that_nothing_is_real(
    served: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["--demo"])

    output = capsys.readouterr().out
    assert "Demo mode" in output
    assert "No model is called" in output


async def test_demo_keeps_its_data_in_memory_only(served: dict[str, Any], tmp_path: Path) -> None:
    cli.main(["--demo"])
    services: Services = served["services"]
    check = await services.checks.create_check("Some claim to look into.")

    assert services.store.get_check(check.id) == check
    assert list(tmp_path.iterdir()) == []
