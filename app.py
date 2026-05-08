"""Streamlit dashboard for the personal job opening collector."""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from job_collector.config import AppConfig
from job_collector.database import JobDatabase
from job_collector.models import Company, JobStatus
from job_collector.scraper import PlaywrightCareerScraper
from job_collector.service import (
    CompanyScanResult,
    JobScanService,
    job_records_to_dataframe,
    load_companies_from_csv,
)


def main() -> None:
    """Run the Streamlit job opening collector dashboard."""
    logger = _configure_logging()
    config = AppConfig()
    database = JobDatabase(config.database_path, logger)
    database.initialize()

    st.set_page_config(page_title="Job Opening Collector", layout="wide")
    st.title("Job Opening Collector")

    companies = _load_configured_companies(config, logger)
    _render_configured_companies(companies)
    _render_scan_controls(config, database, logger, companies)
    _render_job_table(database, companies)


def _configure_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    return logging.getLogger("job_collector")


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


def _render_scan_controls(
    config: AppConfig,
    database: JobDatabase,
    logger: logging.Logger,
    companies: list[Company],
) -> None:
    if st.button("Scan all companies", type="primary"):
        if not companies:
            logger.warning("No valid companies found in %s", config.companies_csv_path)
            st.warning("No valid companies found in the CSV file.")
            return

        scraper = PlaywrightCareerScraper(logger)
        service = JobScanService(scraper, database, logger)
        with st.spinner("Scanning company career pages..."):
            summary = service.scan_companies(companies)

        st.success(
            f"Scan complete: {summary.total_matching_jobs} matching jobs, "
            f"{summary.new_jobs} new, {summary.seen_jobs} seen."
        )
        _render_scan_summary(summary.results)
        failed_companies = [result.company_name for result in summary.results if result.error is not None]
        if failed_companies:
            logger.warning("Failed companies during scan: %s", ", ".join(failed_companies))
            st.warning(f"Could not load: {', '.join(failed_companies)}")
            with st.expander("Load error details"):
                for result in summary.results:
                    if result.error is not None:
                        st.write(f"{result.company_name}: {result.error}")


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


def _render_job_table(database: JobDatabase, companies: list[Company]) -> None:
    try:
        all_records = database.list_jobs()
    except RuntimeError as exc:
        st.error(str(exc))
        return

    all_jobs = job_records_to_dataframe(all_records)

    if all_jobs.empty:
        _render_filters(pd.DataFrame(), companies)
        st.info("No matching jobs stored yet.")
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
