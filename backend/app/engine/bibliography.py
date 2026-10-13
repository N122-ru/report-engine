"""Format bibliography entries according to GOST R 7.0.5-2008.

Each book, article, website, or standard occupies one line. Empty fields
are omitted without leaving redundant separators.
"""

from typing import Optional
import re

from .typography import apply_typography_rules

REFERENCE_KINDS = ("book", "article", "website", "standard")

KIND_LABELS = {
    "book": "Книга",
    "article": "Статья",
    "website": "Сайт",
    "standard": "Стандарт",
}


def _clean(value: Optional[object]) -> str:
    if value is None:
        return ""
    return str(value).strip().rstrip(".")


def normalize_kind(value: Optional[object]) -> str:
    """Normalize the kind, defaulting to book as in the TypeScript mirror."""
    kind = str(value or "").strip().lower()
    return kind if kind in REFERENCE_KINDS else "book"


def _dot(text: str) -> str:
    """Ensure one trailing period without treating abbreviations separately."""
    text = text.strip()
    return text if text.endswith(".") else text + "."


def _join(parts: list) -> str:
    """Join with em dashes without a leading separator or repeated periods."""
    chunks = [p.strip() for p in parts if p and p.strip()]
    if not chunks:
        return "Источник"
    text = chunks[0]
    for chunk in chunks[1:]:
        text += f" – {chunk}"
    return re.sub(r"\.{2,}", ".", text)


def format_reference(ref: dict) -> str:
    """Format a GOST R 7.0.5 entry with the report body's Russian typography."""
    return apply_typography_rules(_compose_reference(ref))


def _compose_reference(ref: dict) -> str:
    """Format a GOST R 7.0.5 entry from dictionary fields."""
    kind = normalize_kind(ref.get("kind"))
    authors_raw = str(ref.get("authors") or "").strip()
    authors = authors_raw
    title = _clean(ref.get("title"))
    place = str(ref.get("place") or "").strip()
    publisher = _clean(ref.get("publisher"))
    year = _clean(ref.get("year"))
    details = _clean(ref.get("details"))
    url = (ref.get("url") or "").strip()

    def _head() -> str:
        head = ""
        if authors:
            head = authors if authors.endswith(".") else authors + "."
        if title:
            head = f"{head} {title}".strip() if head else title
        return head

    if kind == "article":
        # Article order: authors, title, journal, year, issue, pages.
        head = _head()
        if publisher:
            head = f"{head} // {publisher}" if head else publisher
        tail = [_dot(head)] if head else []
        tail += [_dot(p) for p in (year, details) if p]
        return _join(tail)

    if kind == "website":
        # Website entries place the access date after the URL.
        if not title and not url and not details:
            return "Источник"
        head = title or "Электронный ресурс"
        text = f"{head} : [Электронный ресурс]."
        if url:
            text += f" – URL: {url}"
            if details:
                text += f" (дата обращения: {details})"
            text += "."
        elif details:
            text += f" – {details}."
        return re.sub(r"\.{2,}", ".", text)

    # Books and standards share the author/title/publication/details format.
    head = _head()
    pub = publisher
    if place and publisher:
        pub = f"{place}: {publisher}"
    elif place:
        pub = place
    if pub and year:
        pub = f"{pub}, {year}"
    elif year:
        pub = year
    chunks = []
    if head:
        chunks.append(_dot(head))
    if pub:
        chunks.append(_dot(pub))
    if details:
        chunks.append(_dot(details))
    return _join(chunks)
