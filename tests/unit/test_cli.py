"""The command line outside the app itself: version, usage errors, and a missing key."""

import os
import subprocess
import sys
from importlib import metadata

import manyminds

INSTALLED_VERSION = metadata.version("manyminds")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the command in a fresh process that has no API key."""
    env = {name: value for name, value in os.environ.items() if name != "OPENROUTER_API_KEY"}
    return subprocess.run(
        [sys.executable, "-m", "manyminds", *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=env,
    )


def test_package_exposes_the_installed_version() -> None:
    assert getattr(manyminds, "__version__", None) == INSTALLED_VERSION


def test_version_flag_prints_name_and_version_only() -> None:
    result = run_cli("--version")

    assert result.returncode == 0
    assert result.stdout == f"manyminds {INSTALLED_VERSION}\n"


def test_bare_command_without_a_key_explains_how_to_start() -> None:
    result = run_cli()

    assert result.returncode == 1
    assert "OPENROUTER_API_KEY" in result.stderr
    assert "manyminds --demo" in result.stderr
    assert result.stdout == ""


def test_unknown_option_is_rejected_with_usage() -> None:
    result = run_cli("--no-such-option")

    assert result.returncode == 2
    assert "usage: manyminds" in result.stderr
