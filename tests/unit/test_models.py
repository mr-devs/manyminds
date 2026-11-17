"""What a research thread hands back.

Its findings are the agent's own notes. There is no field in which to rule on the claim, and
links the search never returned are listed so that the user can be warned about them.
"""

import pytest
from pydantic import ValidationError

from manyminds.core.models import Report, as_read


def test_findings_are_the_notes_as_written() -> None:
    report = Report(notes="## Findings\n\nTwo archives agree on 1932.")

    assert report.notes == "## Findings\n\nTwo archives agree on 1932."
    assert report.unreturned_links == []


def test_findings_have_no_field_for_a_verdict() -> None:
    assert set(Report.model_fields) == {"notes", "unreturned_links"}


@pytest.mark.parametrize("extra", ["verdict", "rating", "confidence", "label", "score"])
def test_findings_reject_fields_that_rule_on_the_claim(extra: str) -> None:
    with pytest.raises(ValidationError):
        Report.model_validate({"notes": "Some notes.", extra: "true"})


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_findings_cannot_be_blank(blank: str) -> None:
    with pytest.raises(ValidationError):
        Report(notes=blank)


def test_links_the_search_did_not_return_are_kept_with_the_findings() -> None:
    report = Report(
        notes="See https://made-up.example/x", unreturned_links=["https://made-up.example/x"]
    )

    assert report.unreturned_links == ["https://made-up.example/x"]


def test_a_message_is_read_as_its_words_then_what_its_images_showed() -> None:
    assert as_read("Is this real?", ["A stage.", None]) == (
        "Is this real?\n\n"
        "[Attached image 1, as described by a model that looked at it (the description may be "
        "wrong): A stage.]\n\n"
        "[Attached image 2 could not be looked at.]"
    )
    assert as_read("  ", []) == ""
