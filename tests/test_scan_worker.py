"""Tests for the scan subprocess worker helpers."""

import logging
from pathlib import Path

from job_collector.models import Company
from job_collector.scan_worker import load_scan_results, select_companies_by_name, write_scan_summary
from job_collector.service import CompanyScanResult, ScanSummary


def test_select_companies_by_name_preserves_csv_order() -> None:
    """Selected companies should be returned in CSV order, not dropdown order."""
    companies = [
        Company(company_name="SAP", career_url="https://jobs.sap.com/search/?q=software"),
        Company(company_name="Volvo Group", career_url="https://jobs.volvogroup.com/search/?q=software"),
        Company(company_name="Sandvik", career_url="https://www.home.sandvik/en/careers/job-search/?q=software"),
    ]

    selected = select_companies_by_name(companies, ("Sandvik", "SAP"))

    assert [company.company_name for company in selected] == ["SAP", "Sandvik"]


def test_scan_summary_json_round_trip(tmp_path: Path) -> None:
    """Scan worker JSON should round-trip into dashboard scan result objects."""
    result_json_path = tmp_path / "scan_result.json"
    logger = logging.getLogger("test_scan_worker")
    summary = ScanSummary(
        results=(
            CompanyScanResult(company_name="SAP", found_jobs=2, new_jobs=1, seen_jobs=1),
            CompanyScanResult(company_name="Volvo Group", found_jobs=0, new_jobs=0, seen_jobs=0, error="Timeout"),
        ),
        total_matching_jobs=2,
        new_jobs=1,
        seen_jobs=1,
    )

    write_scan_summary(result_json_path, summary, logger)
    results = load_scan_results(result_json_path, logger)

    assert results == summary.results
