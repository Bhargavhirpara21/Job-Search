"""Scanning service that ties CSV input, scraping, parsing, and storage together."""

from collections.abc import Sequence
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Protocol

import pandas as pd

from job_collector.database import JobDatabase
from job_collector.models import Company, JobRecord
from job_collector.parser import extract_visible_job_postings

REQUIRED_COMPANY_COLUMNS: tuple[str, ...] = ("company_name", "career_url")


class CareerPageLoader(Protocol):
    """Interface for loading rendered career page HTML."""

    def fetch_html(self, company: Company) -> str | None:
        """Return rendered HTML for a company career page, or None on failure."""
        ...


@dataclass(frozen=True, slots=True)
class CompanyScanResult:
    """Scan result for one configured company."""

    company_name: str
    found_jobs: int
    new_jobs: int
    seen_jobs: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ScanSummary:
    """Aggregate result for a scan across one or more companies."""

    results: tuple[CompanyScanResult, ...]
    total_matching_jobs: int
    new_jobs: int
    seen_jobs: int


class JobScanService:
    """Coordinate career page scans and persistence of matching jobs."""

    def __init__(self, scraper: CareerPageLoader, database: JobDatabase, logger: logging.Logger) -> None:
        """Create a scan service with explicit scraper, database, and logger dependencies."""
        self._scraper = scraper
        self._database = database
        self._logger = logger

    def scan_companies(self, companies: Sequence[Company]) -> ScanSummary:
        """Scan all companies, storing matching jobs and continuing after load failures."""
        self._database.initialize()
        results: list[CompanyScanResult] = []
        total_matching_jobs = 0
        total_new_jobs = 0
        total_seen_jobs = 0

        for company in companies:
            html = self._load_company_html(company)
            if html is None:
                results.append(
                    CompanyScanResult(
                        company_name=company.company_name,
                        found_jobs=0,
                        new_jobs=0,
                        seen_jobs=0,
                        error="Career page could not be loaded.",
                    )
                )
                continue

            postings = extract_visible_job_postings(html, company)
            company_new_jobs = 0
            company_seen_jobs = 0

            for posting in postings:
                record = self._database.upsert_job(posting)
                if record.status == "new":
                    company_new_jobs += 1
                else:
                    company_seen_jobs += 1

            found_jobs = len(postings)
            total_matching_jobs += found_jobs
            total_new_jobs += company_new_jobs
            total_seen_jobs += company_seen_jobs
            results.append(
                CompanyScanResult(
                    company_name=company.company_name,
                    found_jobs=found_jobs,
                    new_jobs=company_new_jobs,
                    seen_jobs=company_seen_jobs,
                )
            )

        return ScanSummary(
            results=tuple(results),
            total_matching_jobs=total_matching_jobs,
            new_jobs=total_new_jobs,
            seen_jobs=total_seen_jobs,
        )

    def _load_company_html(self, company: Company) -> str | None:
        try:
            return self._scraper.fetch_html(company)
        except RuntimeError as exc:
            self._logger.warning("Could not load %s career page: %s", company.company_name, exc)
            return None
        except ValueError as exc:
            self._logger.warning("Invalid career page response for %s: %s", company.company_name, exc)
            return None


def load_companies_from_csv(csv_path: Path, logger: logging.Logger) -> list[Company]:
    """Load company career page configuration from a CSV file."""
    try:
        dataframe = pd.read_csv(csv_path)
    except FileNotFoundError as exc:
        logger.exception("Company CSV not found: %s", csv_path)
        raise RuntimeError("Company CSV not found") from exc
    except pd.errors.EmptyDataError as exc:
        logger.exception("Company CSV is empty: %s", csv_path)
        raise RuntimeError("Company CSV is empty") from exc
    except pd.errors.ParserError as exc:
        logger.exception("Company CSV could not be parsed: %s", csv_path)
        raise RuntimeError("Company CSV could not be parsed") from exc

    missing_columns = [column for column in REQUIRED_COMPANY_COLUMNS if column not in dataframe.columns]
    if missing_columns:
        raise ValueError(f"Company CSV is missing required columns: {', '.join(missing_columns)}")

    companies: list[Company] = []
    for _, row in dataframe.iterrows():
        company_name = _clean_cell(row.get("company_name"))
        career_url = _clean_cell(row.get("career_url"))
        if company_name is None or career_url is None:
            logger.warning("Skipping company row with missing company_name or career_url")
            continue

        companies.append(
            Company(
                company_name=company_name,
                career_url=career_url,
                location=_clean_cell(row.get("location")),
                notes=_clean_cell(row.get("notes")),
            )
        )

    return companies


def job_records_to_dataframe(records: Sequence[JobRecord]) -> pd.DataFrame:
    """Convert persisted job records to a dashboard-friendly DataFrame."""
    rows = [
        {
            "company_name": record.company_name,
            "job_title": record.job_title,
            "location": record.location or "",
            "job_url": record.job_url,
            "source_career_url": record.source_career_url,
            "date_found": record.date_found,
            "last_checked": record.last_checked,
            "status": record.status,
            "matched_keywords": ", ".join(record.matched_keywords),
        }
        for record in records
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "company_name",
            "job_title",
            "location",
            "job_url",
            "source_career_url",
            "date_found",
            "last_checked",
            "status",
            "matched_keywords",
        ],
    )


def _clean_cell(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None

    cleaned_value = str(value).strip()
    if not cleaned_value:
        return None
    return cleaned_value
