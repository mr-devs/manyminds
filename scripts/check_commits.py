"""Check that commits keep test changes and implementation changes apart.

Usage: check_commits.py [REVISION_RANGE]    (default: origin/main..HEAD)

Rules, applied to every non-merge commit in the range:

* ``test:`` commits may only touch files under ``tests/``. They may add tests and change
  or remove existing ones.
* Any other commit may add files under ``tests/`` but may not modify, rename or delete
  files that already exist there.

So a change to what the tests say is always its own commit, apart from the code it tests.

Exit status: 0 when clean, 1 on violations, 2 when the range cannot be read.
"""

import subprocess
import sys
from dataclasses import dataclass

TESTS_DIR = "tests/"
DEFAULT_RANGE = "origin/main..HEAD"
_PROBLEMS = {
    "M": "modifies an existing test file",
    "D": "deletes an existing test file",
    "R": "renames an existing test file",
    "T": "modifies an existing test file",
}


@dataclass(frozen=True)
class Change:
    status: str
    path: str


@dataclass(frozen=True)
class Commit:
    sha: str
    message: str
    changes: tuple[Change, ...]

    @property
    def subject(self) -> str:
        return self.message.splitlines()[0] if self.message else ""


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return done.stdout


def _read_commit(sha: str) -> Commit:
    message = _git("show", "--no-patch", "--format=%B", sha).strip()
    listing = _git("diff-tree", "--root", "--no-commit-id", "--name-status", "-r", "-M", sha)
    changes = []
    for line in listing.splitlines():
        status, *paths = line.split("\t")
        # For renames and copies the first path is the file that already existed.
        changes.append(Change(status=status[0], path=paths[0]))
    return Commit(sha=sha, message=message, changes=tuple(changes))


def read_commits(revision_range: str) -> list[Commit]:
    shas = _git("rev-list", "--no-merges", "--reverse", revision_range, "--").split()
    return [_read_commit(sha) for sha in shas]


def violations(commit: Commit) -> list[str]:
    subject = commit.subject
    found = []
    if subject.startswith("test:"):
        found += [
            f"{change.path}: a test: commit may only touch {TESTS_DIR}"
            for change in commit.changes
            if not change.path.startswith(TESTS_DIR)
        ]
    else:
        found += [
            f"{change.path}: {_PROBLEMS[change.status]}"
            for change in commit.changes
            if change.path.startswith(TESTS_DIR) and change.status in _PROBLEMS
        ]
    return found


def main(argv: list[str]) -> int:
    revision_range = argv[0] if argv else DEFAULT_RANGE
    try:
        commits = read_commits(revision_range)
    except subprocess.CalledProcessError as error:
        print(f"cannot read revision range {revision_range!r}: {error.stderr}", file=sys.stderr)
        return 2

    failed = False
    for commit in commits:
        problems = violations(commit)
        if problems:
            failed = True
            print(f"{commit.sha[:8]} {commit.subject}")
            for problem in problems:
                print(f"  {problem}")
    if failed:
        return 1
    noun = "commit" if len(commits) == 1 else "commits"
    print(f"{len(commits)} {noun} checked, no violations")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
