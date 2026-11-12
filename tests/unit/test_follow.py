"""Deciding whether a scrolling view is at its end, and so should keep following new content."""

import pytest

from manyminds.ui.follow import is_at_end


def test_a_view_scrolled_to_the_bottom_is_at_the_end() -> None:
    assert is_at_end(position=1400, size=2000, container=600) is True


def test_a_view_within_a_few_pixels_of_the_bottom_counts_as_at_the_end() -> None:
    assert is_at_end(position=1370, size=2000, container=600) is True


@pytest.mark.parametrize("position", [0, 700, 1300])
def test_a_view_scrolled_up_is_not_at_the_end(position: float) -> None:
    assert is_at_end(position=position, size=2000, container=600) is False


def test_content_shorter_than_the_view_is_always_at_the_end() -> None:
    assert is_at_end(position=0, size=300, container=600) is True
