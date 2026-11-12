"""Checks on model output against what the search tool actually returned."""

import re
from collections.abc import Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit

_QUOTE_MARKS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})  # noqa: RUF001
_SPACE = re.compile(r"\s+")

_OMISSION = re.compile(r"\n[ \t]*(?:\.\.\.|\[\.\.\.\])[ \t]*\n")
"""A line holding only `...` or `[...]`: how Exa divides separate parts of one page."""
MIN_QUOTE_LENGTH = 15


def url_key(url: str) -> str:
    """A form of the URL for comparing two references to the same page.

    Ignores letter case in the scheme and host, a trailing slash, the fragment, and tracking
    parameters that providers append (`utm_*`). The host itself must match exactly.
    """
    parts = urlsplit(url.strip())
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.startswith("utm_")
        ]
    )
    key = f"{parts.scheme.lower()}://{(parts.netloc or '').lower()}{parts.path.rstrip('/')}"
    return f"{key}?{query}" if query else key


def _flatten(text: str) -> str:
    plain = text.replace("&lt;", "<").translate(_QUOTE_MARKS)
    return _SPACE.sub(" ", plain).strip().casefold()


def quote_in_passages(quote: str, passages: Sequence[str]) -> bool | None:
    """Whether the quote appears within one passage the search returned.

    Spacing, case and quote-mark style are ignored, and so is the `&lt;` escaping that
    `as_data` applies before a model sees the text. A passage is also divided wherever the
    search engine marked an omission on a line of its own, so a quote cannot bridge a gap.
    Returns None when nothing can be said: there is no passage, or the quote is too short
    to identify one.
    """
    wanted = _flatten(quote)
    if not passages or len(wanted) < MIN_QUOTE_LENGTH:
        return None
    return any(
        wanted in _flatten(piece) for passage in passages for piece in _OMISSION.split(passage)
    )


def as_data(text: str) -> str:
    """Make untrusted text safe to place inside a tagged data block in a prompt."""
    return text.replace("<", "&lt;")
