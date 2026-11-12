"""Keeping a scrolling view pinned to its end while content is added to it.

The browser reports the view's scroll position whenever it changes. A report does not say
why it changed, so the two causes are told apart by what moved: if the position went up,
the user scrolled; if the position stayed put and the content got taller, content arrived.
"""

TOLERANCE = 40
"""Pixels from the bottom that still count as being at the end."""


def is_at_end(*, position: float, size: float, container: float) -> bool:
    """True when the visible part of a view of the given size reaches its bottom."""
    return size - container - position <= TOLERANCE


class Follower:
    """Decides, from scroll reports, whether a view should be moved to its end."""

    def __init__(self) -> None:
        self.following = True
        self._last_position: float | None = None

    def moved(self, *, position: float, size: float, container: float) -> bool:
        """Take one scroll report. Return True if the view should now be moved to its end."""
        at_end = is_at_end(position=position, size=size, container=container)
        scrolled_up = self._last_position is not None and position < self._last_position
        self._last_position = position
        if at_end:
            self.following = True
        elif scrolled_up:
            self.following = False
        return self.following and not at_end
