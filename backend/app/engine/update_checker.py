"""Optional, cached checks for a newer GitHub release."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from ..version import APP_VERSION


UPDATE_URL_ENV = "REPORT_ENGINE_UPDATE_URL"
UPDATE_REPOSITORY_ENV = "REPORT_ENGINE_UPDATE_REPOSITORY"
DEFAULT_UPDATE_REPOSITORY = "N122-ru/report-engine"
UPDATE_CACHE_SECONDS = 6 * 60 * 60
UPDATE_TIMEOUT_SECONDS = 3
MAX_UPDATE_RESPONSE_BYTES = 256 * 1024
_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_VERSION_PATTERN = re.compile(
    r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)


@dataclass(frozen=True)
class _Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...]


@dataclass(frozen=True)
class _CachedResult:
    checked_at: float
    value: dict[str, str | None]


_cache: dict[str, _CachedResult] = {}
_cache_lock = threading.Lock()


def _parse_version(value: str) -> _Version | None:
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if not match:
        return None
    prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
    return _Version(int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease)


def _compare_prerelease(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    if not left and not right:
        return 0
    if not left:
        return 1
    if not right:
        return -1
    for left_part, right_part in zip(left, right):
        if left_part == right_part:
            continue
        left_number = left_part.isdigit()
        right_number = right_part.isdigit()
        if left_number and right_number:
            return 1 if int(left_part) > int(right_part) else -1
        if left_number != right_number:
            return -1 if left_number else 1
        return 1 if left_part > right_part else -1
    return (len(left) > len(right)) - (len(left) < len(right))


def compare_versions(left: str, right: str) -> int:
    """Compare two SemVer values and return -1, 0, or 1."""
    left_version = _parse_version(left)
    right_version = _parse_version(right)
    if left_version is None or right_version is None:
        raise ValueError("Both versions must conform to SemVer")
    left_core = (left_version.major, left_version.minor, left_version.patch)
    right_core = (right_version.major, right_version.minor, right_version.patch)
    if left_core != right_core:
        return (left_core > right_core) - (left_core < right_core)
    return _compare_prerelease(left_version.prerelease, right_version.prerelease)


def _feed_url() -> str | None:
    configured_url = os.environ.get(UPDATE_URL_ENV, "").strip()
    if configured_url:
        return configured_url
    repository = os.environ.get(UPDATE_REPOSITORY_ENV, DEFAULT_UPDATE_REPOSITORY).strip()
    if _REPOSITORY_PATTERN.fullmatch(repository):
        return f"https://api.github.com/repos/{repository}/releases/latest"
    return None


def _valid_http_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password:
        return None
    return value.strip()


def _fetch_release(feed_url: str) -> tuple[str, str | None]:
    valid_feed_url = _valid_http_url(feed_url)
    if valid_feed_url is None:
        raise ValueError("Invalid update feed URL")
    request = Request(
        valid_feed_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Report-Engine-update-checker",
        },
    )
    with urlopen(request, timeout=UPDATE_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read(MAX_UPDATE_RESPONSE_BYTES))
    if not isinstance(payload, dict):
        raise ValueError("Update feed did not return an object")
    raw_version = payload.get("tag_name") or payload.get("latest_version") or payload.get("version")
    parsed_version = _parse_version(raw_version) if isinstance(raw_version, str) else None
    if parsed_version is None:
        raise ValueError("Update feed returned an invalid version")
    normalized_version = f"{parsed_version.major}.{parsed_version.minor}.{parsed_version.patch}"
    if parsed_version.prerelease:
        normalized_version += "-" + ".".join(parsed_version.prerelease)
    release_url = _valid_http_url(payload.get("html_url") or payload.get("release_url"))
    return normalized_version, release_url


def _unavailable() -> dict[str, str | None]:
    return {"status": "unavailable", "latest_version": None, "release_url": None}


def reset_update_cache() -> None:
    """Clear the process cache; intended for tests and controlled reloads."""
    with _cache_lock:
        _cache.clear()


def get_update_info() -> dict[str, str | None]:
    """Return update status without making update availability a hard dependency."""
    feed_url = _feed_url()
    if not feed_url:
        return {"status": "disabled", "latest_version": None, "release_url": None}

    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(feed_url)
        if cached and now - cached.checked_at < UPDATE_CACHE_SECONDS:
            return dict(cached.value)
        try:
            latest_version, release_url = _fetch_release(feed_url)
            status = "available" if compare_versions(APP_VERSION, latest_version) < 0 else "current"
            value = {
                "status": status,
                "latest_version": latest_version,
                "release_url": release_url,
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            value = _unavailable()
        _cache[feed_url] = _CachedResult(now, value)
        return dict(value)
