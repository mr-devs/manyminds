"""Checks on model output against what the search tool actually returned."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit

_QUOTE_MARKS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})  # noqa: RUF001
_SPACE = re.compile(r"\s+")

PASSAGE_BREAK = "[...]"
"""Divides separate passages of one page inside an excerpt. Exa uses the same marker."""
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
    return _SPACE.sub(" ", text.translate(_QUOTE_MARKS)).strip().casefold()


def quote_in_excerpt(quote: str, excerpt: str) -> bool:
    """Whether the quote appears in the excerpt, ignoring spacing, case and quote-mark style.

    An excerpt may hold several separate passages divided by `[...]`; the quote must sit
    inside one of them. A quote too short to identify a passage never counts as found.
    """
    wanted = _flatten(quote)
    if len(wanted) < MIN_QUOTE_LENGTH:
        return False
    return any(wanted in _flatten(passage) for passage in excerpt.split(PASSAGE_BREAK))


def as_data(text: str) -> str:
    """Make untrusted text safe to place inside a tagged data block in a prompt."""
    return text.replace("<", "&lt;")
