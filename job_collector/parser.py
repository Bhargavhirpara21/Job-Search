"""HTML parsing helpers for extracting likely job postings."""

from collections.abc import Iterable
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from job_collector.filters import should_keep_job
from job_collector.models import Company, JobPosting

NOISE_LINK_TEXT: tuple[str, ...] = (
    "apply now",
    "learn more",
    "read more",
    "view details",
    "more details",
    "sign in",
    "login",
    "privacy",
    "cookies",
)


def extract_visible_job_postings(html: str, company: Company) -> list[JobPosting]:
    """Extract broad technical job postings from loaded career page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    _remove_non_visible_elements(soup)

    postings: list[JobPosting] = []
    seen_keys: set[tuple[str, str]] = set()

    for anchor in _iter_candidate_links(soup):
        title = _clean_text(anchor.get_text(" ", strip=True))
        href = str(anchor.get("href", "")).strip()
        if not title or not href or _is_noise_link(title):
            continue

        nearby_text = _nearby_text(anchor)
        keep_job, matched_keywords = should_keep_job(title, nearby_text)
        if not keep_job:
            continue

        job_url = urljoin(company.career_url, href)
        seen_key = (title.lower(), job_url)
        if seen_key in seen_keys:
            continue
        seen_keys.add(seen_key)

        postings.append(
            JobPosting(
                company_name=company.company_name,
                job_title=title,
                location=_extract_location(anchor, company.location),
                job_url=job_url,
                source_career_url=company.career_url,
                matched_keywords=matched_keywords,
            )
        )

    return postings


def _remove_non_visible_elements(soup: BeautifulSoup) -> None:
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()


def _iter_candidate_links(soup: BeautifulSoup) -> Iterable[Tag]:
    for anchor in soup.find_all("a", href=True):
        if isinstance(anchor, Tag):
            yield anchor


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _is_noise_link(title: str) -> bool:
    normalized_title = title.lower()
    return normalized_title in NOISE_LINK_TEXT or len(normalized_title) < 3


def _nearby_text(anchor: Tag) -> str:
    parent = anchor.find_parent(["article", "li", "tr", "section", "div"])
    if parent is None:
        return _clean_text(anchor.get_text(" ", strip=True))
    return _clean_text(parent.get_text(" ", strip=True))


def _extract_location(anchor: Tag, default_location: str | None) -> str | None:
    if default_location:
        return default_location

    parent = anchor.find_parent(["article", "li", "tr", "section", "div"])
    if parent is None:
        return None

    for attribute_name in ("data-location", "data-job-location"):
        attribute_value = parent.get(attribute_name)
        if isinstance(attribute_value, str) and attribute_value.strip():
            return _clean_text(attribute_value)

    for child in parent.find_all(True):
        child_text = _clean_text(child.get_text(" ", strip=True))
        child_location_match = re.fullmatch(
            r"(?:location|standort|ort)\s*[:\-]\s*(.+)",
            child_text,
            re.IGNORECASE,
        )
        if child_location_match is not None:
            return _clean_text(child_location_match.group(1))

    parent_text = _clean_text(parent.get_text(" ", strip=True))
    location_match = re.search(r"(?:location|standort|ort)\s*[:\-]\s*([^|,]+)", parent_text, re.IGNORECASE)
    if location_match is None:
        return None

    return _clean_text(location_match.group(1))
