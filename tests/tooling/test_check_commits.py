"""The commit rule keeps test changes and implementation changes in separate commits.

Each test builds a small real git repository and runs the script against it.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_commits.py"

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "author@example.invalid",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "author@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


class Repo:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.git("init", "--quiet", "--initial-branch=main")
        self.write("README.md", "start\n")
        self.commit("chore: start")
        self.git("tag", "base")

    def git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=self.root, env=GIT_ENV, capture_output=True, text=True, check=True
        )
        return done.stdout

    def write(self, path: str, content: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def commit(self, message: str) -> None:
        self.git("add", "--all")
        self.git("commit", "--quiet", "--message", message)

    def check(self, revision_range: str = "base..HEAD") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), revision_range],
            cwd=self.root,
            env=GIT_ENV,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path)


def test_red_then_green_sequence_passes(repo: Repo) -> None:
    repo.write("tests/test_thing.py", "def test_thing():\n    assert thing() == 1\n")
    repo.commit("test: thing returns one")
    repo.write("src/thing.py", "def thing():\n    return 1\n")
    repo.commit("feat: add thing")

    result = repo.check()

    assert result.returncode == 0
    assert result.stdout == "2 commits checked, no violations\n"


def test_test_commit_touching_source_is_a_violation(repo: Repo) -> None:
    repo.write("tests/test_thing.py", "def test_thing():\n    assert True\n")
    repo.write("src/thing.py", "def thing():\n    return 1\n")
    repo.commit("test: thing returns one")

    result = repo.check()

    assert result.returncode == 1
    assert "test: thing returns one" in result.stdout
    assert "src/thing.py" in result.stdout
    assert "may only touch tests/" in result.stdout


def test_feature_commit_modifying_an_existing_test_is_a_violation(repo: Repo) -> None:
    repo.write("tests/test_thing.py", "def test_thing():\n    assert thing() == 1\n")
    repo.commit("test: thing returns one")
    repo.write("tests/test_thing.py", "def test_thing():\n    assert thing() == 2\n")
    repo.write("src/thing.py", "def thing():\n    return 2\n")
    repo.commit("feat: add thing")

    result = repo.check()

    assert result.returncode == 1
    assert "feat: add thing" in result.stdout
    assert "tests/test_thing.py" in result.stdout
    assert "modifies an existing test file" in result.stdout


def test_feature_commit_deleting_a_test_is_a_violation(repo: Repo) -> None:
    repo.write("tests/test_thing.py", "def test_thing():\n    assert thing() == 1\n")
    repo.commit("test: thing returns one")
    repo.git("rm", "--quiet", "tests/test_thing.py")
    repo.commit("refactor: tidy up")

    result = repo.check()

    assert result.returncode == 1
    assert "refactor: tidy up" in result.stdout
    assert "deletes an existing test file" in result.stdout


def test_feature_commit_renaming_a_test_is_a_violation(repo: Repo) -> None:
    body = "def test_thing():\n    assert thing() == 1\n\n\ndef test_other():\n    assert other()\n"
    repo.write("tests/test_thing.py", body)
    repo.commit("test: thing returns one")
    repo.git("mv", "tests/test_thing.py", "tests/disabled_thing.py")
    repo.commit("chore: move files")

    result = repo.check()

    assert result.returncode == 1
    assert "chore: move files" in result.stdout
    assert "tests/test_thing.py" in result.stdout


def test_non_test_commit_may_add_new_files_under_tests(repo: Repo) -> None:
    repo.write("tests/fixtures/sample.json", "{}\n")
    repo.commit("chore: add fixture")

    result = repo.check()

    assert result.returncode == 0


def test_approved_test_fix_may_modify_tests(repo: Repo) -> None:
    repo.write("tests/test_thing.py", "def test_thing():\n    assert thing() == 1\n")
    repo.commit("test: thing returns one")
    repo.write("tests/test_thing.py", "def test_thing():\n    assert thing() == 2\n")
    repo.commit("test-fix: thing should return two\n\nApproved: owner confirmed the spec says two")

    result = repo.check()

    assert result.returncode == 0


def test_test_fix_without_approval_line_is_a_violation(repo: Repo) -> None:
    repo.write("tests/test_thing.py", "def test_thing():\n    assert thing() == 1\n")
    repo.commit("test: thing returns one")
    repo.write("tests/test_thing.py", "def test_thing():\n    assert thing() == 2\n")
    repo.commit("test-fix: thing should return two")

    result = repo.check()

    assert result.returncode == 1
    assert "needs a line starting 'Approved:'" in result.stdout


def test_test_fix_touching_source_is_a_violation(repo: Repo) -> None:
    repo.write("tests/test_thing.py", "def test_thing():\n    assert True\n")
    repo.write("src/thing.py", "def thing():\n    return 1\n")
    repo.commit("test-fix: adjust\n\nApproved: owner said so")

    result = repo.check()

    assert result.returncode == 1
    assert "may only touch tests/" in result.stdout


def test_only_commits_in_the_given_range_are_checked(repo: Repo) -> None:
    repo.write("tests/test_thing.py", "def test_thing():\n    assert True\n")
    repo.write("src/thing.py", "def thing():\n    return 1\n")
    repo.commit("test: mixed commit before the range")
    repo.git("tag", "later")
    repo.write("src/other.py", "x = 1\n")
    repo.commit("feat: other")

    result = repo.check("later..HEAD")

    assert result.returncode == 0
    assert result.stdout == "1 commit checked, no violations\n"


def test_range_reaching_the_first_commit_is_checked(repo: Repo) -> None:
    result = repo.check("HEAD")

    assert result.returncode == 0
    assert result.stdout == "1 commit checked, no violations\n"


def test_unknown_revision_is_an_error_not_a_pass(repo: Repo) -> None:
    result = repo.check("no-such-branch..HEAD")

    assert result.returncode == 2
    assert "cannot read revision range 'no-such-branch..HEAD'" in result.stderr
    assert "no violations" not in result.stdout
