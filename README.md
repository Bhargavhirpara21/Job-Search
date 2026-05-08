# Job Opening Collector

A small Streamlit app that scans configured company career pages, keeps broad Software / IT / Computer Engineering related postings, stores them in SQLite, and shows which jobs are new or already seen.

This is intentionally simple. It does not rank jobs, make fit decisions, or use AI matching.

## Setup

```powershell
pip install -r requirements.txt
playwright install chromium
streamlit run app.py
```

## Company List

Edit `data/companies.csv` with these columns:

```csv
company_name,career_url,location,notes
Example Company,https://example.com/careers,Global,Optional note
```

`company_name` and `career_url` are required. `location` and `notes` are optional.

## How It Works

- Playwright loads each career page with Chromium.
- BeautifulSoup parses visible links and nearby text.
- Broad technical keywords keep jobs in software, IT, data, AI, cloud, DevOps, embedded, QA, cybersecurity, automation, and related fields.
- Clearly unrelated title keywords filter out jobs like HR, sales, marketing, finance, legal, warehouse, logistics, procurement, and customer service.
- Results are stored in `data/jobs.sqlite3`.
- Duplicate jobs are detected using `company_name + job_title + job_url`.
- First-time jobs are stored as `new`; jobs found again in a later scan are updated to `seen`.

Some career sites may block automation, require login, use CAPTCHA, or hide jobs behind APIs that this v1 parser cannot read. Those companies are logged and skipped without stopping the full scan.

## Run

```powershell
streamlit run app.py
```

Use the dashboard to choose one or more companies from `data/companies.csv`, scan jobs, filter by company/status/title, open original job postings, and export the current table to CSV.

The dashboard does not show old stored jobs on first load. It shows results after a scan succeeds in the current browser session.
