"""SQLite persistence for discovered jobs."""

from collections.abc import Sequence
from datetime import datetime
import logging
from pathlib import Path
import sqlite3

from job_collector.models import JobPosting, JobRecord, JobStatus


class JobDatabase:
    """SQLite-backed repository for job postings."""

    def __init__(self, database_path: Path, logger: logging.Logger) -> None:
        """Create a repository using the given SQLite database path."""
        self._database_path = database_path
        self._logger = logger

    def initialize(self) -> None:
        """Create the jobs table and indexes when they do not exist."""
        try:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._logger.exception("Could not create database directory: %s", self._database_path.parent)
            raise RuntimeError("Could not create database directory") from exc

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_name TEXT NOT NULL,
                        job_title TEXT NOT NULL,
                        location TEXT,
                        job_url TEXT NOT NULL,
                        source_career_url TEXT NOT NULL,
                        date_found TEXT NOT NULL,
                        last_checked TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('new', 'seen')),
                        matched_keywords TEXT NOT NULL,
                        UNIQUE(company_name, job_title, job_url)
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_jobs_company_status ON jobs(company_name, status)"
                )
        except sqlite3.Error as exc:
            self._logger.exception("Could not initialize SQLite database: %s", self._database_path)
            raise RuntimeError("Could not initialize SQLite database") from exc

    def upsert_job(self, job: JobPosting, checked_at: datetime | None = None) -> JobRecord:
        """Insert a new job or mark an existing one as seen after a scan."""
        scan_time = checked_at or datetime.now()
        last_checked = scan_time.isoformat(timespec="seconds")
        matched_keywords = _serialize_keywords(job.matched_keywords)

        try:
            with self._connect() as connection:
                existing = connection.execute(
                    """
                    SELECT id, date_found
                    FROM jobs
                    WHERE company_name = ? AND job_title = ? AND job_url = ?
                    """,
                    (job.company_name, job.job_title, job.job_url),
                ).fetchone()

                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO jobs (
                            company_name,
                            job_title,
                            location,
                            job_url,
                            source_career_url,
                            date_found,
                            last_checked,
                            status,
                            matched_keywords
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?)
                        """,
                        (
                            job.company_name,
                            job.job_title,
                            job.location,
                            job.job_url,
                            job.source_career_url,
                            scan_time.date().isoformat(),
                            last_checked,
                            matched_keywords,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE jobs
                        SET location = ?,
                            source_career_url = ?,
                            last_checked = ?,
                            status = 'seen',
                            matched_keywords = ?
                        WHERE id = ?
                        """,
                        (
                            job.location,
                            job.source_career_url,
                            last_checked,
                            matched_keywords,
                            int(existing["id"]),
                        ),
                    )

                row = connection.execute(
                    """
                    SELECT *
                    FROM jobs
                    WHERE company_name = ? AND job_title = ? AND job_url = ?
                    """,
                    (job.company_name, job.job_title, job.job_url),
                ).fetchone()
        except sqlite3.Error as exc:
            self._logger.exception("Could not upsert job %s for %s", job.job_title, job.company_name)
            raise RuntimeError("Could not upsert job") from exc

        if row is None:
            raise RuntimeError("Could not load job after upsert")
        return _row_to_record(row)

    def list_jobs(
        self,
        company_name: str | None = None,
        status: JobStatus | None = None,
        title_search: str | None = None,
    ) -> list[JobRecord]:
        """List persisted jobs with optional company, status, and title filters."""
        where_clauses: list[str] = []
        parameters: list[str] = []

        if company_name:
            where_clauses.append("company_name = ?")
            parameters.append(company_name)
        if status:
            where_clauses.append("status = ?")
            parameters.append(status)
        if title_search:
            where_clauses.append("LOWER(job_title) LIKE ?")
            parameters.append(f"%{title_search.lower()}%")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"SELECT * FROM jobs {where_sql} ORDER BY date_found DESC, company_name, job_title"

        try:
            with self._connect() as connection:
                rows = connection.execute(query, parameters).fetchall()
        except sqlite3.Error as exc:
            self._logger.exception("Could not list jobs from SQLite")
            raise RuntimeError("Could not list jobs") from exc

        return [_row_to_record(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _serialize_keywords(keywords: Sequence[str]) -> str:
    return ", ".join(keywords)


def _deserialize_keywords(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    return tuple(keyword.strip() for keyword in value.split(",") if keyword.strip())


def _row_to_record(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        id=int(row["id"]),
        company_name=str(row["company_name"]),
        job_title=str(row["job_title"]),
        location=str(row["location"]) if row["location"] is not None else None,
        job_url=str(row["job_url"]),
        source_career_url=str(row["source_career_url"]),
        date_found=str(row["date_found"]),
        last_checked=str(row["last_checked"]),
        status=row["status"],
        matched_keywords=_deserialize_keywords(str(row["matched_keywords"])),
    )

