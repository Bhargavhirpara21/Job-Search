"""Subprocess entry point for running scans outside the Streamlit thread."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import logging
from pathlib import Path

from job_collector.database import JobDatabase
from job_collector.models import Company
from job_collector.scraper import PlaywrightCareerScraper
from job_collector.service import CompanyScanResult, JobScanService, ScanSummary, load_companies_from_csv


def main() -> int:
    """Run a scan from command-line arguments and write a JSON result file."""
    logger = _configure_logging()
    parser = _build_parser()
    args = parser.parse_args()

    try:
        run_scan_worker(
            companies_csv_path=Path(args.companies_csv),
            database_path=Path(args.database),
            result_json_path=Path(args.result_json),
            selected_company_names=tuple(args.company),
            logger=logger,
        )
    except (RuntimeError, ValueError, OSError) as exc:
        logger.exception("Scan worker failed")
        _write_worker_failure(Path(args.result_json), str(exc), logger)
        return 1

    return 0


def run_scan_worker(
    companies_csv_path: Path,
    database_path: Path,
    result_json_path: Path,
    selected_company_names: Sequence[str],
    logger: logging.Logger,
) -> ScanSummary:
    """Run the scan workflow for selected companies and write the result JSON."""
    companies = load_companies_from_csv(companies_csv_path, logger)
    selected_companies = select_companies_by_name(companies, selected_company_names)
    if not selected_companies:
        raise ValueError("No companies selected for scanning")

    database = JobDatabase(database_path, logger)
    scraper = PlaywrightCareerScraper(logger)
    service = JobScanService(scraper, database, logger)
    summary = service.scan_companies(selected_companies)
    write_scan_summary(result_json_path, summary, logger)
    return summary


def select_companies_by_name(companies: Sequence[Company], selected_company_names: Sequence[str]) -> list[Company]:
    """Return companies whose names were selected, preserving CSV order."""
    selected_names = {company_name.strip() for company_name in selected_company_names if company_name.strip()}
    if not selected_names:
        return list(companies)

    configured_names = {company.company_name for company in companies}
    missing_names = sorted(selected_names - configured_names)
    if missing_names:
        raise ValueError(f"Selected companies are not in the CSV: {', '.join(missing_names)}")

    return [company for company in companies if company.company_name in selected_names]


def write_scan_summary(result_json_path: Path, summary: ScanSummary, logger: logging.Logger) -> None:
    """Write a scan summary to a JSON file for the Streamlit parent process."""
    payload = {
        "ok": True,
        "total_matching_jobs": summary.total_matching_jobs,
        "new_jobs": summary.new_jobs,
        "seen_jobs": summary.seen_jobs,
        "results": [_scan_result_to_dict(result) for result in summary.results],
    }
    _write_json(result_json_path, payload, logger)


def load_scan_results(result_json_path: Path, logger: logging.Logger) -> tuple[CompanyScanResult, ...]:
    """Load scan results written by the subprocess worker."""
    try:
        payload = json.loads(result_json_path.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.exception("Could not read scan result file: %s", result_json_path)
        raise RuntimeError("Could not read scan result file") from exc
    except json.JSONDecodeError as exc:
        logger.exception("Scan result file is not valid JSON: %s", result_json_path)
        raise RuntimeError("Scan result file is not valid JSON") from exc

    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("Scan result file does not contain a results list")

    return tuple(_scan_result_from_dict(result) for result in raw_results)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a job collector scan")
    parser.add_argument("--companies-csv", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--result-json", required=True)
    parser.add_argument("--company", action="append", default=[])
    return parser


def _configure_logging() -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    return logging.getLogger("job_collector.scan_worker")


def _write_worker_failure(result_json_path: Path, error: str, logger: logging.Logger) -> None:
    payload = {"ok": False, "error": error, "results": []}
    try:
        _write_json(result_json_path, payload, logger)
    except RuntimeError:
        logger.warning("Could not write worker failure result")


def _write_json(result_json_path: Path, payload: dict[str, object], logger: logging.Logger) -> None:
    try:
        result_json_path.parent.mkdir(parents=True, exist_ok=True)
        result_json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.exception("Could not write scan result file: %s", result_json_path)
        raise RuntimeError("Could not write scan result file") from exc


def _scan_result_to_dict(result: CompanyScanResult) -> dict[str, object]:
    return {
        "company_name": result.company_name,
        "found_jobs": result.found_jobs,
        "new_jobs": result.new_jobs,
        "seen_jobs": result.seen_jobs,
        "error": result.error,
    }


def _scan_result_from_dict(value: object) -> CompanyScanResult:
    if not isinstance(value, dict):
        raise ValueError("Scan result entry is not an object")

    return CompanyScanResult(
        company_name=str(value.get("company_name", "")),
        found_jobs=int(value.get("found_jobs", 0)),
        new_jobs=int(value.get("new_jobs", 0)),
        seen_jobs=int(value.get("seen_jobs", 0)),
        error=str(value["error"]) if value.get("error") is not None else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
