"""Report and evidence validation.

A report is structured evidence for the user to judge: a neutral summary, quoted and linked
evidence, and what could not be determined. It carries no verdict of any kind.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from manyminds.core.models import EvidenceItem, Report, Stance


def evidence(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "url": "https://example.org/history/bridge",
        "title": "Bridge history",
        "quote": "The bridge opened to traffic in March 1932.",
        "stance": "supports",
    }
    item.update(overrides)
    return item


def report(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "summary": "Two archives give an opening date in 1932.",
        "evidence": [evidence()],
        "undetermined": "Whether construction finished on schedule.",
    }
    data.update(overrides)
    return data


def without(data: dict[str, Any], key: str) -> dict[str, Any]:
    return {name: value for name, value in data.items() if name != key}


def test_valid_report_is_accepted() -> None:
    parsed = Report.model_validate(report())

    assert parsed.summary == "Two archives give an opening date in 1932."
    assert parsed.undetermined == "Whether construction finished on schedule."
    assert len(parsed.evidence) == 1
    item = parsed.evidence[0]
    assert item.url == "https://example.org/history/bridge"
    assert item.title == "Bridge history"
    assert item.quote == "The bridge opened to traffic in March 1932."
    assert item.stance is Stance.SUPPORTS


def test_report_has_exactly_three_fields_and_none_is_a_verdict() -> None:
    assert set(Report.model_fields) == {"summary", "evidence", "undetermined"}


@pytest.mark.parametrize("extra", ["verdict", "confidence", "rating", "conclusion"])
def test_report_rejects_fields_that_rule_on_the_claim(extra: str) -> None:
    with pytest.raises(ValidationError):
        Report.model_validate(report(**{extra: "supported"}))


@pytest.mark.parametrize("field", ["summary", "undetermined", "evidence"])
def test_report_requires_every_field(field: str) -> None:
    with pytest.raises(ValidationError):
        Report.model_validate(without(report(), field))


@pytest.mark.parametrize("field", ["summary", "undetermined"])
@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_report_rejects_blank_text(field: str, blank: str) -> None:
    with pytest.raises(ValidationError):
        Report.model_validate(report(**{field: blank}))


def test_report_may_have_no_evidence_when_nothing_was_found() -> None:
    parsed = Report.model_validate(
        report(evidence=[], undetermined="No relevant sources were found.")
    )

    assert parsed.evidence == []


@pytest.mark.parametrize("field", ["url", "quote", "stance"])
def test_evidence_requires_url_quote_and_stance(field: str) -> None:
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(without(evidence(), field))


@pytest.mark.parametrize("blank", ["", "   "])
def test_evidence_rejects_blank_quote(blank: str) -> None:
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(evidence(quote=blank))


def test_evidence_title_is_optional() -> None:
    parsed = EvidenceItem.model_validate(without(evidence(), "title"))

    assert parsed.title is None


def test_evidence_text_is_trimmed() -> None:
    parsed = EvidenceItem.model_validate(
        evidence(quote="  quoted words \n", url=" https://a.example/x ")
    )

    assert parsed.quote == "quoted words"
    assert parsed.url == "https://a.example/x"


@pytest.mark.parametrize("url", ["https://example.org/a?b=1#c", "http://example.org"])
def test_evidence_accepts_http_and_https_urls(url: str) -> None:
    assert EvidenceItem.model_validate(evidence(url=url)).url == url


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "ftp://example.org/file",
        "//example.org/page",
        "example.org/page",
        "https://",
        "https:///path-only",
        "",
    ],
)
def test_evidence_rejects_urls_that_are_not_http_or_https(url: str) -> None:
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(evidence(url=url))


@pytest.mark.parametrize("stance", ["supports", "undermines"])
def test_evidence_stance_is_supports_or_undermines(stance: str) -> None:
    assert EvidenceItem.model_validate(evidence(stance=stance)).stance.value == stance


@pytest.mark.parametrize("stance", ["neutral", "true", "SUPPORTS", ""])
def test_evidence_rejects_other_stances(stance: str) -> None:
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(evidence(stance=stance))


def test_evidence_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(evidence(credibility="high"))


def test_evidence_grounding_flags_default_to_unchecked() -> None:
    parsed = EvidenceItem.model_validate(evidence())

    assert parsed.grounded is False
    assert parsed.quote_matched is None
