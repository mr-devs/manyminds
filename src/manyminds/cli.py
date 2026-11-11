"""Console entry point."""

import argparse
from collections.abc import Sequence

from manyminds import __version__

NOTICE = """\
This is a pre-alpha release that only claims the package name.
The application is not usable yet.
Follow progress at https://github.com/mr-devs/manyminds"""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="manyminds",
        description="Gather cited evidence about claims found on the web (pre-alpha).",
    )
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    args = parser.parse_args(argv)

    print(f"manyminds {__version__}")
    if not args.version:
        print(NOTICE)
    return 0
