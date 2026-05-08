"""Tests for broad technical keyword filtering."""

from job_collector.filters import should_keep_job


def test_keeps_broad_software_job() -> None:
    """Software engineering titles should pass the broad technical filter."""
    keep_job, matched_keywords = should_keep_job(
        "Senior Software Engineer",
        "Cloud platform team building backend services.",
    )

    assert keep_job is True
    assert "software" in matched_keywords
    assert "engineer" in matched_keywords
    assert "cloud" in matched_keywords


def test_excludes_unrelated_title_even_with_technical_context() -> None:
    """Excluded title families should be removed before keyword matching."""
    keep_job, matched_keywords = should_keep_job(
        "Sales Engineer",
        "Works with software customers and cloud products.",
    )

    assert keep_job is False
    assert matched_keywords == ()


def test_it_keyword_uses_word_boundary() -> None:
    """The IT keyword should match standalone IT and not substrings."""
    keep_it_job, matched_keywords = should_keep_job("IT Support Specialist", "")
    keep_marketing_job, _ = should_keep_job("Marketing Specialist", "")

    assert keep_it_job is True
    assert "IT" in matched_keywords
    assert keep_marketing_job is False

