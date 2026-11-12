"""Console entry point."""

import argparse
import os
import sys
from collections.abc import Sequence

from manyminds import __version__

KEY_VARIABLE = "OPENROUTER_API_KEY"
DATA_DIR_VARIABLE = "MANYMINDS_DATA_DIR"

NO_KEY = f"""\
manyminds needs an OpenRouter API key to run.
Set it in your shell and start again:

    export {KEY_VARIABLE}=...    (create a key at https://openrouter.ai/keys)
    manyminds

To look around without a key, run: manyminds --demo"""

BAD_KEY = f"""\
{KEY_VARIABLE} contains characters that cannot be part of a key, such as spaces,
curly quotes or an ellipsis. Copy the key again and set it without quotes around it."""

ALREADY_RUNNING = """\
manyminds is already running with this data folder:
    {folder}
Use the window that is already open, or stop that copy first."""

BAD_FOLDER = f"""\
The data folder could not be used ({{reason}}):
    {{folder}}
Check that it is a folder you can write to, or set {DATA_DIR_VARIABLE} to another one."""

BAD_DATABASE = f"""\
The saved checks could not be opened ({{reason}}):
    {{database}}
The file may be damaged. Move it aside to start afresh, or set {DATA_DIR_VARIABLE} to
another folder."""

DISCLOSURE = (
    "Text you paste is sent to OpenRouter, to the model provider behind each model you "
    "choose, and to Exa, which runs the web searches and opens links. The app runs only on "
    "this computer, and your "
    "checks are saved on this computer."
)

START_NOTICE = f"""\
{DISCLOSURE}
They are kept in: {{folder}}
Each lead costs roughly one to two US cents on your OpenRouter account.
Press Ctrl+C to stop."""

DECOMPOSE_MODEL = "openai/gpt-6-luna"
RESEARCH_MODELS = (
    "openai/gpt-6-luna",
    "anthropic/claude-haiku-5.5",
    "google/gemini-3.5-flash-lite",
    "deepseek/deepseek-v4-flash",
    "anthropic/claude-sonnet-5.5",
    "openai/gpt-6.1-terra",
)

DEMO_NOTICE = """\
Demo mode. No model is called, nothing is searched and nothing is saved:
leads and reports are placeholders. Press Ctrl+C to stop."""

DEMO_MODEL = "demo/model"
DEMO_DISCLOSURE = "Demo mode: no model is called, nothing is searched and nothing is saved."


def _run_demo(port: int | None, show: bool) -> None:
    # Imported here so that `manyminds --version` does not load the interface toolkit.
    from manyminds.core.fake import FakeModelClient
    from manyminds.core.services import build_services
    from manyminds.core.storage import Store
    from manyminds.ui import app

    services = build_services(
        store=Store(":memory:"),
        model=FakeModelClient(),
        research_models=[DEMO_MODEL],
        decompose_model=DEMO_MODEL,
        notice=DEMO_DISCLOSURE,
    )
    print(DEMO_NOTICE)
    app.run(services, port=port, show=show)


def _run_real(api_key: str, port: int | None, show: bool) -> int:
    import sqlite3

    from manyminds.core.openrouter.client import build_client
    from manyminds.core.paths import (
        DATABASE_NAME,
        AlreadyRunningError,
        data_dir,
        hold_instance_lock,
        open_store,
    )
    from manyminds.core.services import build_services
    from manyminds.ui import app

    folder = data_dir()
    try:
        # Held until the process ends, so a second copy cannot start on the same data.
        lock = hold_instance_lock(folder)
    except AlreadyRunningError:
        print(ALREADY_RUNNING.format(folder=folder), file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error) as error:
        print(BAD_FOLDER.format(folder=folder, reason=type(error).__name__), file=sys.stderr)
        return 1
    try:
        store = open_store(folder)
        # Nothing is running yet, so work still marked as under way was cut off last time.
        store.interrupt_unfinished_jobs()
        store.fail_pending_messages()
    except (OSError, sqlite3.Error) as error:
        lock.close()
        database = folder / DATABASE_NAME
        print(BAD_DATABASE.format(database=database, reason=type(error).__name__), file=sys.stderr)
        return 1
    # The HTTP client lives as long as the process, which ends when the server stops.
    model, _ = build_client(api_key)
    services = build_services(
        store=store,
        model=model,
        research_models=RESEARCH_MODELS,
        decompose_model=DECOMPOSE_MODEL,
        notice=DISCLOSURE,
    )
    print(START_NOTICE.format(folder=folder))
    app.run(services, port=port, show=show)
    lock.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="manyminds",
        description="Gather cited evidence about claims found on the web (alpha).",
    )
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    parser.add_argument(
        "--demo", action="store_true", help="try the app with placeholder data and no API key"
    )
    parser.add_argument("--port", type=int, help="port to serve on (default: a free port)")
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open a browser window on start"
    )
    args = parser.parse_args(argv)

    if args.version:
        print(f"manyminds {__version__}")
        return 0
    if args.demo:
        _run_demo(args.port, show=not args.no_browser)
        return 0
    api_key = os.environ.get(KEY_VARIABLE, "").strip()
    if not api_key:
        print(NO_KEY, file=sys.stderr)
        return 1
    if not (api_key.isascii() and api_key.isprintable() and " " not in api_key):
        print(BAD_KEY, file=sys.stderr)
        return 1
    return _run_real(api_key, args.port, show=not args.no_browser)
