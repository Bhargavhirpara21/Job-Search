"""Tests for the scan service and company CSV loading."""

import logging
from pathlib import Path

from job_collector.database import JobDatabase
from job_collector.models import Company
from job_collector.service import JobScanService, load_companies_from_csv


class _FakeScraper:
    pages: dict[str, str | None]
    errors: dict[str, str]

    def __init__(self, pages: dict[str, str | None], errors: dict[str, str] | None = None) -> None:
        self.pages = pages
        self.errors = errors or {}

    def fetch_html(self, company: Company) -> str | None:
        return self.pages.get(company.company_name)

    def get_last_error(self, company: Company) -> str | None:
        return self.errors.get(company.company_name)


def test_scan_service_saves_jobs_and_continues_after_failed_pages(tmp_path: Path) -> None:
    """Scanning should persist matching jobs and report failed company pages."""
    logger = logging.getLogger("test_service")
    database = JobDatabase(tmp_path / "jobs.sqlite3", logger)
    scraper = _FakeScraper(
        {
            "GoodCo": """
            <html>
              <body>
                <article>
                  <a href="/jobs/platform-engineer">Platform Engineer</a>
                  <span>Location: Stockholm</span>
                </article>
              </body>
            </html>
            """,
            "BrokenCo": None,
        },
        {"BrokenCo": "Playwright browser driver could not start."},
    )
    service = JobScanService(scraper, database, logger)
    companies = (
        Company(company_name="GoodCo", career_url="https://good.example/careers"),
        Company(company_name="BrokenCo", career_url="https://broken.example/careers"),
    )

    summary = service.scan_companies(companies)
    records = database.list_jobs()

    assert summary.total_matching_jobs == 1
    assert summary.new_jobs == 1
    assert summary.seen_jobs == 0
    assert summary.results[1].error == "Playwright browser driver could not start."
    assert len(records) == 1
    assert records[0].job_title == "Platform Engineer"
    assert records[0].status == "new"


def test_scan_service_marks_existing_jobs_as_seen_on_next_scan(tmp_path: Path) -> None:
    """A second scan of the same job should update the existing row to seen."""
    logger = logging.getLogger("test_service_seen")
    database = JobDatabase(tmp_path / "jobs.sqlite3", logger)
    scraper = _FakeScraper(
        {
            "GoodCo": """
            <html>
              <body>
                <article>
                  <a href="/jobs/software-developer">Software Developer</a>
                </article>
              </body>
            </html>
            """,
        }
    )
    service = JobScanService(scraper, database, logger)
    companies = (Company(company_name="GoodCo", career_url="https://good.example/careers"),)

    first_summary = service.scan_companies(companies)
    second_summary = service.scan_companies(companies)
    records = database.list_jobs()

    assert first_summary.new_jobs == 1
    assert second_summary.new_jobs == 0
    assert second_summary.seen_jobs == 1
    assert len(records) == 1
    assert records[0].status == "seen"


def test_load_companies_from_csv_reads_required_and_optional_columns(tmp_path: Path) -> None:
    """CSV loading should read required fields and optional metadata."""
    csv_path = tmp_path / "companies.csv"
    csv_path.write_text(
        "company_name,career_url,location,notes\n"
        "ExampleCo,https://example.com/careers,Berlin,Main portal\n",
        encoding="utf-8",
    )

    companies = load_companies_from_csv(csv_path, logging.getLogger("test_csv"))

    assert companies == [
        Company(
            company_name="ExampleCo",
            career_url="https://example.com/careers",
            location="Berlin",
            notes="Main portal",
        )
    ]
