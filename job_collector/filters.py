"""Broad software and IT keyword filtering for job postings."""

from collections.abc import Sequence
import re

DEFAULT_INCLUDE_KEYWORDS: tuple[str, ...] = (
    "software",
    "developer",
    "engineer",
    "programmer",
    "IT",
    "computer science",
    "computer engineering",
    "backend",
    "frontend",
    "full stack",
    "full-stack",
    "cloud",
    "DevOps",
    "data",
    "data engineer",
    "data analyst",
    "data scientist",
    "machine learning",
    "AI",
    "artificial intelligence",
    "computer vision",
    "automation",
    "embedded",
    "firmware",
    "QA engineer",
    "test automation",
    "application developer",
    "system engineer",
    "database",
    "cybersecurity",
    "security engineer",
    "SAP developer",
    "platform engineer",
    "infrastructure engineer",
    "R&D software",
    "digitalization",
)

DEFAULT_EXCLUDE_TITLE_KEYWORDS: tuple[str, ...] = (
    "HR",
    "recruiter",
    "talent acquisition",
    "sales",
    "marketing",
    "accounting",
    "finance",
    "controlling",
    "legal",
    "warehouse",
    "logistics",
    "buyer",
    "category buyer",
    "purchasing",
    "procurement",
    "customer service",
    "office manager",
    "business development",
    "key account",
    "receptionist",
)


def should_keep_job(
    title: str,
    nearby_text: str,
    include_keywords: Sequence[str] = DEFAULT_INCLUDE_KEYWORDS,
    exclude_title_keywords: Sequence[str] = DEFAULT_EXCLUDE_TITLE_KEYWORDS,
) -> tuple[bool, tuple[str, ...]]:
    """Return whether a job should be kept and the technical keywords matched."""
    if is_excluded_title(title, exclude_title_keywords):
        return False, ()

    matched_keywords = find_matching_keywords(title, nearby_text, include_keywords)
    return bool(matched_keywords), tuple(matched_keywords)


def is_excluded_title(
    title: str,
    exclude_title_keywords: Sequence[str] = DEFAULT_EXCLUDE_TITLE_KEYWORDS,
) -> bool:
    """Return true when the title clearly belongs to an unrelated job family."""
    normalized_title = _normalize_text(title)
    return any(_contains_keyword(normalized_title, keyword) for keyword in exclude_title_keywords)


def find_matching_keywords(
    title: str,
    nearby_text: str,
    include_keywords: Sequence[str] = DEFAULT_INCLUDE_KEYWORDS,
) -> list[str]:
    """Find broad technical keywords in the job title or nearby page text."""
    haystack = _normalize_text(f"{title} {nearby_text}")
    matched_keywords: list[str] = []

    for keyword in include_keywords:
        if _contains_keyword(haystack, keyword):
            matched_keywords.append(keyword)

    return matched_keywords


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _contains_keyword(text: str, keyword: str) -> bool:
    normalized_keyword = _normalize_text(keyword)
    escaped_keyword = re.escape(normalized_keyword).replace(r"\ ", r"\s+")
    starts_with_word = normalized_keyword[0].isalnum()
    ends_with_word = normalized_keyword[-1].isalnum()

    prefix = r"(?<![a-z0-9])" if starts_with_word else ""
    suffix = r"(?![a-z0-9])" if ends_with_word else ""
    pattern = f"{prefix}{escaped_keyword}{suffix}"
    return re.search(pattern, text) is not None
