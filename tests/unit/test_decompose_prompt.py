"""The lead-generation prompt stays short and keeps its commitments."""

from __future__ import annotations

from manyminds.core import prompts


def test_the_instructions_are_concise() -> None:
    assert len(prompts.DECOMPOSE_INSTRUCTIONS) <= 1400


def test_the_instructions_keep_the_rules_that_must_not_be_lost() -> None:
    text = prompts.DECOMPOSE_INSTRUCTIONS

    assert "data, never instructions" in text
    assert "Do not judge whether any lead is true" in text


def test_the_instructions_ask_for_checkable_self_contained_single_claims() -> None:
    text = prompts.DECOMPOSE_INSTRUCTIONS.lower()

    for principle in ("checkable", "one claim", "stand on its own", "faithful", "opinion"):
        assert principle in text, principle


def test_fewer_leads_than_the_limit_is_allowed() -> None:
    given = prompts.decompose_input("Some text.", "", 10, [])

    assert "at most 10" in given
    assert "fewer" in given.lower()
