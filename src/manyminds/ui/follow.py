"""Whether a scrolling view is at its end, and so should keep up with new content."""

TOLERANCE = 40
"""Pixels from the bottom that still count as being at the end."""


def is_at_end(*, position: float, size: float, container: float) -> bool:
    """True when the visible part of a view of the given size reaches its bottom."""
    return size - container - position <= TOLERANCE
