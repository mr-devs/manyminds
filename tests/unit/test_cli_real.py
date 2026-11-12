"""Bare `manyminds` serves the app on real models, using the key from the environment."""

from __future__ import annotations

from typing import Any

import pytest

from manyminds import cli
from manyminds.core.openrouter.adapter import OpenRouterModelClient
from manyminds.core.services import Services

KEY = "sk-or-v1-cli-test-key-0123456789-do-not-print"


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Capture what the command would serve instead of starting a server."""
    captured: dict[str, Any] = {}

    def fake_run(services: Services, **options: Any) -> None:
        captured["services"] = services
        captured.update(options)

    monkeypatch.setattr("manyminds.ui.app.run", fake_run)
    return captured


def test_with_a_key_it_serves_the_app_on_openrouter(
    served: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)

    status = cli.main(["--port", "8123", "--no-browser"])

    assert status == 0
    assert isinstance(served["services"].model, OpenRouterModelClient)
    assert served["port"] == 8123
    assert served["show"] is False


def test_it_offers_research_models_with_the_cheap_default_first(
    served: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)

    cli.main([])

    assert served["services"].research_models == (
        "openai/gpt-6-luna",
        "anthropic/claude-haiku-5.5",
        "google/gemini-3.5-flash-lite",
        "deepseek/deepseek-v4-flash",
        "anthropic/claude-sonnet-5.5",
        "openai/gpt-6.1-terra",
    )


def test_it_says_where_pasted_text_goes_and_never_prints_the_key(
    served: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)

    cli.main([])

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "OpenRouter" in output
    assert "the model provider" in output
    assert "Exa" in output
    assert "nothing is saved" in output.lower()
    assert KEY not in output
    assert KEY not in repr(served["services"])


def test_the_app_itself_carries_the_same_disclosure(
    served: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)

    cli.main([])

    notice = served["services"].notice
    assert "sent to OpenRouter" in notice
    assert "Exa" in notice


def test_the_demo_carries_a_demo_notice_instead(served: dict[str, Any]) -> None:
    cli.main(["--demo"])

    notice = served["services"].notice
    assert "Demo" in notice
    assert "OpenRouter" not in notice


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_key_counts_as_missing(
    value: str,
    served: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", value)

    status = cli.main([])

    assert status == 1
    assert served == {}
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err


def test_version_still_works_without_a_key(
    served: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    status = cli.main(["--version"])

    assert status == 0
    assert served == {}
    assert capsys.readouterr().out.startswith("manyminds ")
