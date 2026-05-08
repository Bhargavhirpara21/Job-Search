"""Application configuration objects."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Filesystem configuration for the collector application."""

    data_dir: Path = Path("data")
    companies_csv_path: Path = Path("data/companies.csv")
    database_path: Path = Path("data/jobs.sqlite3")

