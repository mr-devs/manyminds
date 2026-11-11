"""The 0.0.1 command line: it reports its version and says plainly that it is pre-alpha."""

import subprocess
import sys
from importlib import metadata

import manyminds

INSTALLED_VERSION = metadata.version("manyminds")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "manyminds", *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_package_exposes_the_installed_version() -> None:
    assert getattr(manyminds, "__version__", None) == INSTALLED_VERSION


def test_version_flag_prints_name_and_version_only() -> None:
    result = run_cli("--version")

    assert result.returncode == 0
    assert result.stdout == f"manyminds {INSTALLED_VERSION}\n"


def test_bare_command_prints_version_and_pre_alpha_notice() -> None:
    result = run_cli()

    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert lines[0] == f"manyminds {INSTALLED_VERSION}"
    notice = " ".join(lines[1:])
    assert "pre-alpha" in notice
    assert "not usable yet" in notice
    assert "https://github.com/mr-devs/manyminds" in notice


def test_unknown_option_is_rejected_with_usage() -> None:
    result = run_cli("--no-such-option")

    assert result.returncode == 2
    assert "usage: manyminds" in result.stderr
