"""Playwright-powered career page loading."""

import logging

from playwright.sync_api import Browser, Error as PlaywrightError
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from job_collector.models import Company


class PlaywrightCareerScraper:
    """Load career pages with Chromium and return their rendered HTML."""

    _last_errors_by_company: dict[str, str]

    def __init__(self, logger: logging.Logger, timeout_ms: int = 30_000, headless: bool = True) -> None:
        """Create a scraper with explicit logging and browser settings."""
        self._logger = logger
        self._timeout_ms = timeout_ms
        self._headless = headless
        self._last_errors_by_company = {}

    def fetch_html(self, company: Company) -> str | None:
        """Return rendered HTML for a company career page, or None when loading fails."""
        browser: Browser | None = None
        self._last_errors_by_company.pop(company.company_name, None)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self._headless)
                page = browser.new_page()
                page.goto(company.career_url, wait_until="domcontentloaded", timeout=self._timeout_ms)
                self._wait_for_page_settle(page)
                html = page.content()
                browser.close()
                browser = None
                return html
        except PlaywrightTimeoutError as exc:
            self._record_load_error(company, "Timed out while loading the career page.", exc)
            return None
        except PlaywrightError as exc:
            self._record_load_error(company, "Playwright could not load the career page.", exc)
            return None
        except OSError as exc:
            self._record_load_error(company, "Operating system error while loading the career page.", exc)
            return None
        except AttributeError as exc:
            self._record_load_error(company, "Playwright browser driver could not start.", exc)
            return None
        finally:
            if browser is not None:
                self._close_browser(browser, company)

    def get_last_error(self, company: Company) -> str | None:
        """Return the last load error recorded for a company in this scraper instance."""
        return self._last_errors_by_company.get(company.company_name)

    def _wait_for_page_settle(self, page: Page) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=min(self._timeout_ms, 5_000))
        except PlaywrightTimeoutError:
            self._logger.debug("Page did not reach networkidle before parsing; continuing with current HTML")

    def _close_browser(self, browser: Browser, company: Company) -> None:
        try:
            browser.close()
        except PlaywrightError as exc:
            self._logger.debug("Could not close browser after loading %s: %s", company.company_name, exc)

    def _record_load_error(self, company: Company, message: str, exc: Exception) -> None:
        detail = f"{message} {exc}"
        self._last_errors_by_company[company.company_name] = detail
        self._logger.warning("%s: %s", company.company_name, detail)
