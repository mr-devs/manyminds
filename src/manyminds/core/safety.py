"""Comparing addresses, and making untrusted text safe to put in a prompt."""

from urllib.parse import parse_qsl, urlencode, urlsplit


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


def as_data(text: str) -> str:
    """Make untrusted text safe to place inside a tagged data block in a prompt."""
    return text.replace("<", "&lt;")
