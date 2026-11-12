"""Where the app keeps its data on this computer."""

import os
import sqlite3
from pathlib import Path

import platformdirs

from manyminds.core.storage import Store

DATA_DIR_VARIABLE = "MANYMINDS_DATA_DIR"
DATABASE_NAME = "manyminds.db"
LOCK_NAME = "manyminds.lock"


class AlreadyRunningError(RuntimeError):
    """Another copy of the app is using this data folder."""


def data_dir() -> Path:
    """The folder for saved checks: the user's own data folder unless the environment says."""
    chosen = os.environ.get(DATA_DIR_VARIABLE, "").strip()
    if chosen:
        return Path(chosen).expanduser()
    return Path(platformdirs.user_data_dir("manyminds", appauthor=False))


def _ensure_folder(folder: Path) -> None:
    """Create the folder if it is missing, private to this user.

    A folder that already exists is left exactly as it is: it may be the user's own choice
    and hold other things.
    """
    if not folder.is_dir():
        folder.mkdir(parents=True)
        folder.chmod(0o700)


def _private_file(path: Path) -> None:
    """Make sure the file exists and only this user can read it. Links are not followed."""
    if not path.exists():
        path.touch(mode=0o600)
    if not path.is_symlink():
        path.chmod(0o600)


def hold_instance_lock(folder: Path) -> sqlite3.Connection:
    """Claim the data folder for this process, or raise AlreadyRunningError.

    Two copies sharing one database would each treat the other's running work as cut off.
    The claim is a lock on a small file beside the database. It is released when the returned
    connection is closed or the process ends, however it ends.
    """
    _ensure_folder(folder)
    _private_file(folder / LOCK_NAME)
    lock = sqlite3.connect(str(folder / LOCK_NAME), timeout=0, isolation_level=None)
    try:
        lock.execute("BEGIN EXCLUSIVE")
    except sqlite3.OperationalError:
        lock.close()
        raise AlreadyRunningError(str(folder)) from None
    return lock


def open_store(folder: Path) -> Store:
    """Open the database in the folder, creating both if needed.

    Pasted text and reports are personal, so the database file is readable by this user only.
    """
    _ensure_folder(folder)
    database = folder / DATABASE_NAME
    _private_file(database)
    return Store(database)
