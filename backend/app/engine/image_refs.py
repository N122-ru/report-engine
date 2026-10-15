"""Normalize and resolve Markdown image references across report transports."""

import os
import re
from collections.abc import Iterable
from urllib.parse import unquote


def decode_image_ref(value: str) -> str:
    """Decode a Markdown image target without rejecting malformed escapes."""
    try:
        return unquote(value.strip().strip("<>"))
    except (TypeError, ValueError):
        return value.strip().strip("<>")


def image_ref_basename(value: str) -> str:
    """Return the decoded filename portion of a Markdown image target."""
    return os.path.basename(decode_image_ref(value).replace("\\", "/"))


def canonical_image_name(value: str) -> str:
    """Return the transport-neutral comparison key for one image filename."""
    return re.sub(r"[\W_]+", "", image_ref_basename(value).lower())


def resolve_image_name(reference: str, names: Iterable[str]) -> str | None:
    """Resolve one image reference only when its normalized name is unambiguous."""
    available = list(names)
    decoded = decode_image_ref(reference)
    basename = image_ref_basename(decoded)
    candidates = [reference, decoded, basename]

    for candidate in candidates:
        exact = [name for name in available if name == candidate]
        if len(exact) == 1:
            return exact[0]
        case_insensitive = [name for name in available if name.lower() == candidate.lower()]
        if len(case_insensitive) == 1:
            return case_insensitive[0]

    key = canonical_image_name(reference)
    if not key:
        return None
    matches = [name for name in available if canonical_image_name(name) == key]
    return matches[0] if len(matches) == 1 else None
