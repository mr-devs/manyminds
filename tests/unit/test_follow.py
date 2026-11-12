"""Deciding whether a scrolling view is at its end, and so should keep following new content."""

import pytest

from manyminds.ui.follow import Follower, is_at_end


def test_a_view_scrolled_to_the_bottom_is_at_the_end() -> None:
    assert is_at_end(position=1400, size=2000, container=600) is True


def test_a_view_within_a_few_pixels_of_the_bottom_counts_as_at_the_end() -> None:
    assert is_at_end(position=1370, size=2000, container=600) is True


@pytest.mark.parametrize("position", [0, 700, 1300])
def test_a_view_scrolled_up_is_not_at_the_end(position: float) -> None:
    assert is_at_end(position=position, size=2000, container=600) is False


def test_content_shorter_than_the_view_is_always_at_the_end() -> None:
    assert is_at_end(position=0, size=300, container=600) is True


# -- Follower: telling the user's scrolling apart from the content growing -----------------


def test_a_new_view_is_following() -> None:
    assert Follower().following is True


def test_the_first_report_before_the_jump_has_landed_asks_for_the_jump_again() -> None:
    follower = Follower()

    assert follower.moved(position=0, size=2000, container=600) is True
    assert follower.following is True


def test_a_report_at_the_end_asks_for_nothing() -> None:
    follower = Follower()

    assert follower.moved(position=1400, size=2000, container=600) is False
    assert follower.following is True


def test_content_growing_while_at_the_end_asks_to_move_to_the_new_end() -> None:
    follower = Follower()
    follower.moved(position=1400, size=2000, container=600)

    assert follower.moved(position=1400, size=2600, container=600) is True
    assert follower.following is True


def test_the_position_moving_up_means_the_user_scrolled_and_stops_following() -> None:
    follower = Follower()
    follower.moved(position=1400, size=2000, container=600)

    assert follower.moved(position=900, size=2000, container=600) is False
    assert follower.following is False


def test_content_growing_after_the_user_scrolled_up_asks_for_nothing() -> None:
    follower = Follower()
    follower.moved(position=1400, size=2000, container=600)
    follower.moved(position=900, size=2000, container=600)

    assert follower.moved(position=900, size=2600, container=600) is False
    assert follower.following is False


def test_scrolling_down_part_of_the_way_does_not_resume_following() -> None:
    follower = Follower()
    follower.moved(position=1400, size=2000, container=600)
    follower.moved(position=200, size=2000, container=600)

    assert follower.moved(position=700, size=2000, container=600) is False
    assert follower.following is False


def test_reaching_the_end_again_resumes_following() -> None:
    follower = Follower()
    follower.moved(position=1400, size=2000, container=600)
    follower.moved(position=200, size=2000, container=600)

    assert follower.moved(position=1400, size=2000, container=600) is False
    assert follower.following is True
    assert follower.moved(position=1400, size=2600, container=600) is True
