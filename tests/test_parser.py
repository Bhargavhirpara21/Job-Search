"""Tests for simple career-page HTML parsing."""

from job_collector.models import Company
from job_collector.parser import extract_visible_job_postings


def test_extracts_matching_job_links_and_skips_unrelated_jobs() -> None:
    """Parser should keep broad technical jobs and skip unrelated titles."""
    html = """
    <html>
      <body>
        <section>
          <a href="/jobs/software-engineer">Software Engineer</a>
          <span>Location: Berlin</span>
          <p>Backend cloud platform role.</p>
        </section>
        <section>
          <a href="/jobs/sales-manager">Sales Manager</a>
          <span>Location: Hamburg</span>
        </section>
      </body>
    </html>
    """
    company = Company(company_name="ExampleCo", career_url="https://example.com/careers")

    jobs = extract_visible_job_postings(html, company)

    assert len(jobs) == 1
    assert jobs[0].company_name == "ExampleCo"
    assert jobs[0].job_title == "Software Engineer"
    assert jobs[0].job_url == "https://example.com/jobs/software-engineer"
    assert jobs[0].location == "Berlin"
    assert "software" in jobs[0].matched_keywords

