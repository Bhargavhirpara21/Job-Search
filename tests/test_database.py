"""Tests for SQLite job persistence."""

from datetime import datetime
import logging
from pathlib import Path

from job_collector.database import JobDatabase
from job_collector.models import JobPosting


def test_upsert_inserts_new_job_then_marks_duplicate_seen(tmp_path: Path) -> None:
    """Duplicate company/title/url jobs should update metadata instead of duplicating rows."""
    database = JobDatabase(tmp_path / "jobs.sqlite3", logging.getLogger("test_database"))
    database.initialize()
    job = JobPosting(
        company_name="ExampleCo",
        job_title="Software Engineer",
        location="Berlin",
        job_url="https://example.com/jobs/software-engineer",
        source_career_url="https://example.com/careers",
        matched_keywords=("software", "engineer"),
    )

    first_record = database.upsert_job(job, datetime(2026, 5, 8, 10, 0, 0))
    second_record = database.upsert_job(job, datetime(2026, 5, 9, 10, 0, 0))
    records = database.list_jobs()

    assert first_record.status == "new"
    assert second_record.status == "seen"
    assert second_record.date_found == "2026-05-08"
    assert second_record.last_checked == "2026-05-09T10:00:00"
    assert len(records) == 1
    assert records[0].matched_keywords == ("software", "engineer")
