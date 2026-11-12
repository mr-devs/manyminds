"""Bare `manyminds` serves the app on real models, using the key from the environment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from manyminds import cli
from manyminds.core.openrouter.adapter import OpenRouterModelClient
from manyminds.core.services import Services

KEY = "sk-or-v1-cli-test-key-0123456789-do-not-print"


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Capture what the command would serve instead of starting a server."""
    captured: dict[str, Any] = {}

    def fake_run(services: Services, **options: Any) -> None:
        captured["services"] = services
        captured.update(options)

    monkeypatch.setattr("manyminds.ui.app.run", fake_run)
    monkeypatch.setenv("MANYMINDS_DATA_DIR", str(tmp_path / "data"))
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
    assert "saved on this computer" in output
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


@pytest.mark.parametrize("value", ["sk-or-v1-abc…", "“sk-or-v1-abc”", "sk or v1"])
def test_a_key_that_cannot_be_sent_is_refused_without_printing_it(
    value: str,
    served: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", value)

    status = cli.main([])

    error = capsys.readouterr().err
    assert status == 1
    assert served == {}
    assert "OPENROUTER_API_KEY" in error
    assert "characters" in error
    assert value not in error


def test_checks_are_kept_in_the_data_folder_and_the_start_message_names_it(
    served: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)

    cli.main([])

    assert (tmp_path / "data" / "manyminds.db").is_file()
    assert str(tmp_path / "data") in capsys.readouterr().out


def test_starting_marks_work_cut_off_last_time_as_interrupted(
    served: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from manyminds.core.models import ErrorKind, SearchEngine
    from manyminds.core.paths import open_store

    earlier = open_store(tmp_path / "data")
    check = earlier.create_check_with_leads(
        title="T", source_text="Some text.", instructions="", leads=["Lead A"]
    )
    _, jobs = earlier.launch_leads(
        check.id, models=["vendor/model-a"], search_engine=SearchEngine.EXA, instructions=""
    )
    earlier.close()
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)

    cli.main([])

    job = served["services"].store.get_job(jobs[0].id)
    assert job.error_kind is ErrorKind.INTERRUPTED


def test_starting_marks_a_reply_cut_off_last_time_as_stopped(
    served: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from manyminds.core.models import MessageStatus
    from manyminds.core.paths import open_store

    earlier = open_store(tmp_path / "data")
    check = earlier.create_check_with_leads(
        title="T", source_text="Some text.", instructions="", leads=["Lead A"]
    )
    awaited = earlier.begin_turn(check.id, "Summarise.")
    earlier.close()
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)

    cli.main([])

    reply = served["services"].store.get_message(awaited.id)
    assert reply.status is MessageStatus.FAILED
    assert reply.error_message == "Stopped because the app was closed."


def test_a_database_that_fails_on_first_use_gets_the_short_message(
    served: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import sqlite3

    folder = tmp_path / "data"
    folder.mkdir()
    # Marked as up to date, so opening it succeeds, but its tables are not there.
    with sqlite3.connect(folder / "manyminds.db") as raw:
        raw.execute("PRAGMA user_version = 99")
    raw.close()
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)

    status = cli.main([])

    assert status == 1
    assert "The saved checks could not be opened" in capsys.readouterr().err
    assert "services" not in served
