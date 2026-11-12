"""Where the app keeps its data on this computer."""

import os
from pathlib import Path

import platformdirs

from manyminds.core.storage import Store

DATA_DIR_VARIABLE = "MANYMINDS_DATA_DIR"
DATABASE_NAME = "manyminds.db"


def data_dir() -> Path:
    """The folder for saved checks: the user's own data folder unless the environment says."""
    chosen = os.environ.get(DATA_DIR_VARIABLE, "").strip()
    if chosen:
        return Path(chosen).expanduser()
    return Path(platformdirs.user_data_dir("manyminds", appauthor=False))


def open_store(folder: Path) -> Store:
    """Open the database in the folder, creating both so that only this user can read them.

    Pasted text and reports are personal, so neither is left readable by other accounts.
    """
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o700)
    database = folder / DATABASE_NAME
    database.touch(mode=0o600, exist_ok=True)
    database.chmod(0o600)
    return Store(database)
