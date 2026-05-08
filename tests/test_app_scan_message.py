"""Tests for dashboard scan outcome messages."""

from app import _build_scan_message
from job_collector.service import CompanyScanResult


def test_scan_message_reports_all_failed_scan_without_implying_empty_results() -> None:
    """All-failed scans should be shown as live scan failures, not successful zero-result scans."""
    results = (
        CompanyScanResult("SAP", found_jobs=0, new_jobs=0, seen_jobs=0, error="Playwright failed"),
        CompanyScanResult("Volvo Group", found_jobs=0, new_jobs=0, seen_jobs=0, error="Playwright failed"),
    )

    level, message = _build_scan_message(results)

    assert level == "error"
    assert "Live scan failed" in message
    assert "No job table was refreshed" in message


def test_scan_message_reports_partial_failures_as_warning() -> None:
    """Partially successful scans should keep the counts and mention failed companies."""
    results = (
        CompanyScanResult("SAP", found_jobs=5, new_jobs=3, seen_jobs=2),
        CompanyScanResult("Volvo Group", found_jobs=0, new_jobs=0, seen_jobs=0, error="Timeout"),
    )

    level, message = _build_scan_message(results)

    assert level == "warning"
    assert "5 matching jobs" in message
    assert "1 companies could not be loaded" in message
