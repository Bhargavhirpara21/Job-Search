"""Streamlit dashboard for the personal job opening collector."""

from __future__ import annotations

from collections.abc import Sequence
import logging
from pathlib import Path
import subprocess
import sys

import pandas as pd
import streamlit as st

from job_collector.config import AppConfig
from job_collector.database import JobDatabase
from job_collector.models import Company, JobStatus
from job_collector.scan_worker import load_scan_results
from job_collector.service import CompanyScanResult, job_records_to_dataframe, load_companies_from_csv


def main() -> None:
    """Run the Streamlit job opening collector dashboard."""
    logger = _configure_logging()
    config = AppConfig()
    database = JobDatabase(config.database_path, logger)
    database.initialize()

    st.set_page_config(page_title="Job Opening Collector", layout="wide")
    st.title("Job Opening Collector")

    _initialize_session_state()
    companies = _load_configured_companies(config, logger)
    _render_configured_companies(companies)
    _render_scan_controls(config, logger, companies)
    _render_scan_feedback(companies)

    if bool(st.session_state["show_jobs"]):
        _render_job_table(database, companies, tuple(st.session_state["last_selected_company_names"]))
    else:
        st.info("Choose one or more companies from the CSV, then click Scan jobs.")


def _configure_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    return logging.getLogger("job_collector")


def _initialize_session_state() -> None:
    if "show_jobs" not in st.session_state:
        st.session_state["show_jobs"] = False
    if "last_scan_results" not in st.session_state:
        st.session_state["last_scan_results"] = ()
    if "last_selected_company_names" not in st.session_state:
        st.session_state["last_selected_company_names"] = ()


def _load_configured_companies(config: AppConfig, logger: logging.Logger) -> list[Company]:
    try:
        return load_companies_from_csv(config.companies_csv_path, logger)
    except (RuntimeError, ValueError) as exc:
        logger.warning("Could not load companies CSV for dashboard filters: %s", exc)
        st.error(str(exc))
        return []


def _render_configured_companies(companies: list[Company]) -> None:
    if not companies:
        st.warning("No valid companies found in the CSV file.")
        return

    with st.expander(f"Configured companies from CSV ({len(companies)})"):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "company_name": company.company_name,
                        "career_url": company.career_url,
                        "location": company.location or "",
                        "notes": company.notes or "",
                    }
                    for company in companies
                ]
            ),
            hide_index=True,
            use_container_width=True,
            column_config={"career_url": st.column_config.LinkColumn("career_url")},
        )


def _render_scan_controls(config: AppConfig, logger: logging.Logger, companies: list[Company]) -> None:
    company_names = [company.company_name for company in companies]
    selected_company_names = st.multiselect(
        "Companies to scan",
        company_names,
        default=company_names,
        help="Loaded from data/companies.csv.",
    )

    if st.button("Scan jobs", type="primary"):
        if not companies:
            logger.warning("No valid companies found in %s", config.companies_csv_path)
            st.warning("No valid companies found in the CSV file.")
            return
        if not selected_company_names:
            st.warning("Choose at least one company to scan.")
            return

        with st.spinner("Scanning company career pages..."):
            results = _run_scan_worker(config, tuple(selected_company_names), logger)

        st.session_state["last_scan_results"] = results
        st.session_state["last_selected_company_names"] = tuple(selected_company_names)
        st.session_state["show_jobs"] = bool(results) and not _all_scan_results_failed(results)


def _render_scan_feedback(companies: list[Company]) -> None:
    results = tuple(st.session_state["last_scan_results"])
    if not results:
        return

    message_level, message = _build_scan_message(results)
    if message_level == "error":
        st.error(message)
    elif message_level == "warning":
        st.warning(message)
    else:
        st.success(message)

    _render_scan_summary(results)
    failed_companies = [result.company_name for result in results if result.error is not None]
    if failed_companies:
        st.warning(f"Could not load: {', '.join(failed_companies)}")
        with st.expander("Load error details", expanded=len(failed_companies) == len(companies)):
            for result in results:
                if result.error is not None:
                    st.write(f"{result.company_name}: {result.error}")


def _run_scan_worker(
    config: AppConfig,
    selected_company_names: Sequence[str],
    logger: logging.Logger,
) -> tuple[CompanyScanResult, ...]:
    result_json_path = config.data_dir / "last_scan_result.json"
    command = _build_scan_worker_command(config, result_json_path, selected_company_names)

    try:
        completed_process = subprocess.run(
            command,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("Scan worker timed out: %s", exc)
        return _failed_results(selected_company_names, "Scan worker timed out after 300 seconds.")
    except OSError as exc:
        logger.warning("Could not start scan worker: %s", exc)
        return _failed_results(selected_company_names, f"Could not start scan worker: {exc}")

    if completed_process.stderr.strip():
        logger.warning("Scan worker stderr: %s", completed_process.stderr.strip())

    try:
        results = load_scan_results(result_json_path, logger)
    except (RuntimeError, ValueError) as exc:
        logger.warning("Could not load scan worker results: %s", exc)
        return _failed_results(selected_company_names, str(exc))

    if completed_process.returncode != 0 and not results:
        return _failed_results(selected_company_names, completed_process.stderr.strip() or "Scan worker failed.")

    return results


def _build_scan_worker_command(
    config: AppConfig,
    result_json_path: Path,
    selected_company_names: Sequence[str],
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "job_collector.scan_worker",
        "--companies-csv",
        str(config.companies_csv_path),
        "--database",
        str(config.database_path),
        "--result-json",
        str(result_json_path),
    ]
    for company_name in selected_company_names:
        command.extend(["--company", company_name])
    return command


def _failed_results(selected_company_names: Sequence[str], error: str) -> tuple[CompanyScanResult, ...]:
    return tuple(
        CompanyScanResult(
            company_name=company_name,
            found_jobs=0,
            new_jobs=0,
            seen_jobs=0,
            error=error,
        )
        for company_name in selected_company_names
    )


def _all_scan_results_failed(results: Sequence[CompanyScanResult]) -> bool:
    return bool(results) and all(result.error is not None for result in results)


def _render_scan_summary(results: tuple[CompanyScanResult, ...]) -> None:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "company_name": result.company_name,
                    "scan_status": "failed" if result.error else "loaded",
                    "matching_jobs": result.found_jobs,
                    "new_jobs": result.new_jobs,
                    "seen_jobs": result.seen_jobs,
                    "error": result.error or "",
                }
                for result in results
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )


def _build_scan_message(results: tuple[CompanyScanResult, ...]) -> tuple[str, str]:
    total_matching_jobs = sum(result.found_jobs for result in results)
    new_jobs = sum(result.new_jobs for result in results)
    seen_jobs = sum(result.seen_jobs for result in results)
    failed_companies = [result for result in results if result.error is not None]

    if results and len(failed_companies) == len(results):
        return "error", "Live scan failed for all selected companies. No job table was refreshed."

    message = f"Scan complete: {total_matching_jobs} matching jobs, {new_jobs} new, {seen_jobs} seen."
    if failed_companies:
        return "warning", f"{message} {len(failed_companies)} companies could not be loaded."

    return "success", message


def _render_job_table(
    database: JobDatabase,
    companies: list[Company],
    visible_company_names: Sequence[str],
) -> None:
    try:
        all_records = database.list_jobs()
    except RuntimeError as exc:
        st.error(str(exc))
        return

    all_jobs = job_records_to_dataframe(all_records)
    if visible_company_names and not all_jobs.empty:
        all_jobs = all_jobs[all_jobs["company_name"].isin(tuple(visible_company_names))]

    if all_jobs.empty:
        _render_filters(pd.DataFrame(), companies)
        st.info("No matching jobs were stored for the latest successful scan.")
        return

    selected_company, selected_status, title_search = _render_filters(all_jobs, companies)
    filtered_jobs = _filter_jobs(all_jobs, selected_company, selected_status, title_search)

    if filtered_jobs.empty:
        st.info("No jobs match the current filters.")
        return

    st.dataframe(
        filtered_jobs,
        hide_index=True,
        use_container_width=True,
        column_config={
            "job_url": st.column_config.LinkColumn("Job posting"),
            "source_career_url": st.column_config.LinkColumn("Source page"),
        },
    )
    st.download_button(
        "Export results to CSV",
        data=filtered_jobs.to_csv(index=False).encode("utf-8"),
        file_name="job_openings.csv",
        mime="text/csv",
    )


def _render_filters(dataframe: pd.DataFrame, companies: list[Company]) -> tuple[str, str, str]:
    company_options = _build_company_filter_options(dataframe, companies)
    status_options = ["All", "new", "seen"]

    company_column, status_column, search_column = st.columns([1, 1, 2])
    with company_column:
        selected_company = st.selectbox("Company", company_options)
    with status_column:
        selected_status = st.selectbox("Status", status_options)
    with search_column:
        title_search = st.text_input("Search job title", "")

    return selected_company, selected_status, title_search


def _build_company_filter_options(dataframe: pd.DataFrame, companies: list[Company]) -> list[str]:
    configured_company_names = [company.company_name for company in companies]
    stored_company_names: list[str] = []
    if "company_name" in dataframe.columns:
        stored_company_names = [str(company) for company in dataframe["company_name"].dropna().unique()]

    company_names = sorted(set(configured_company_names + stored_company_names))
    return ["All"] + company_names


def _filter_jobs(
    dataframe: pd.DataFrame,
    selected_company: str,
    selected_status: str,
    title_search: str,
) -> pd.DataFrame:
    filtered_jobs = dataframe.copy()

    if selected_company != "All":
        filtered_jobs = filtered_jobs[filtered_jobs["company_name"] == selected_company]
    if selected_status != "All":
        status_value: JobStatus = "new" if selected_status == "new" else "seen"
        filtered_jobs = filtered_jobs[filtered_jobs["status"] == status_value]
    if title_search.strip():
        filtered_jobs = filtered_jobs[
            filtered_jobs["job_title"].str.contains(title_search.strip(), case=False, na=False, regex=False)
        ]

    return filtered_jobs


if __name__ == "__main__":
    main()
