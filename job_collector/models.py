"""Typed domain models for companies and job postings."""

from dataclasses import dataclass
from typing import Literal

JobStatus = Literal["new", "seen"]


@dataclass(frozen=True, slots=True)
class Company:
    """A company career page configured by the user."""

    company_name: str
    career_url: str
    location: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class JobPosting:
    """A matching job posting discovered on a company career page."""

    company_name: str
    job_title: str
    location: str | None
    job_url: str
    source_career_url: str
    matched_keywords: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JobRecord:
    """A job posting persisted in SQLite with scan metadata."""

    id: int
    company_name: str
    job_title: str
    location: str | None
    job_url: str
    source_career_url: str
    date_found: str
    last_checked: str
    status: JobStatus
    matched_keywords: tuple[str, ...]

