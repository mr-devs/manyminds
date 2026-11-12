"""Console entry point."""

import argparse
from collections.abc import Sequence

from manyminds import __version__

NOTICE = """\
This is a pre-alpha release that only claims the package name.
The application is not usable yet.
Follow progress at https://github.com/mr-devs/manyminds"""

DEMO_NOTICE = """\
Demo mode. No model is called, nothing is searched and nothing is saved:
leads and reports are placeholders. Press Ctrl+C to stop."""

DEMO_MODEL = "demo/model"


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
    )
    print(DEMO_NOTICE)
    app.run(services, port=port, show=show)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="manyminds",
        description="Gather cited evidence about claims found on the web (pre-alpha).",
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

    if args.demo and not args.version:
        _run_demo(args.port, show=not args.no_browser)
        return 0

    print(f"manyminds {__version__}")
    if not args.version:
        print(NOTICE)
    return 0
