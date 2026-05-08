"""Tests for Streamlit dashboard helper behavior."""

import pandas as pd

from app import _build_company_filter_options
from job_collector.models import Company


def test_company_filter_options_include_all_csv_companies_without_jobs() -> None:
    """Company filter should include configured companies even before they have stored jobs."""
    dataframe = pd.DataFrame(
        [
            {"company_name": "SAP"},
            {"company_name": "Volvo Group"},
        ]
    )
    companies = [
        Company(company_name="SAP", career_url="https://jobs.sap.com/search/?q=software"),
        Company(company_name="Volvo Group", career_url="https://jobs.volvogroup.com/search/?q=software"),
        Company(company_name="Sandvik", career_url="https://www.home.sandvik/en/careers/job-search/?q=software"),
        Company(
            company_name="Ericsson",
            career_url="https://www.ericsson.com/en/careers/job-opportunities?query=software",
        ),
    ]

    options = _build_company_filter_options(dataframe, companies)

    assert options == ["All", "Ericsson", "SAP", "Sandvik", "Volvo Group"]
