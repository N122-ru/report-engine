"""Limit abuse and server overload from DDoS, OOM, ReDoS, and request floods."""

import os
import time
import asyncio
from typing import Dict, List
from collections import defaultdict
from fastapi import Request, HTTPException
from .image_input import MAX_IMAGE_SIZE, MAX_IMAGES_COUNT

# -------------------------------------------------------------
# Data and file limits protect against memory exhaustion and ReDoS.
# -------------------------------------------------------------
MAX_MARKDOWN_SIZE = 500 * 1024            # 500 KB (~150 pages; typically 20–50 KB).
MAX_AUTOFIX_SIZE = 500 * 1024             # 500 KB of text for autofix.
MAX_VERIFY_SIZE = 25 * 1024 * 1024        # 25 MB per uploaded DOCX audit.

# Limit parallel LibreOffice conversions to avoid OOM: more than two or three
# instances can trigger Linux's OOM killer on a VPS with 1–2 GB RAM.
PDF_SEMAPHORE = asyncio.Semaphore(2)


class SimpleRateLimiter:
    """Apply a sliding-window rate limit in memory without an external database."""
    def __init__(self):
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._last_cleanup = time.monotonic()
        self._lock = asyncio.Lock()

    async def is_allowed(self, ip: str, max_requests: int, window_seconds: int = 60) -> bool:
        # Allow explicit disabling, including in tests.
        if os.getenv("DISABLE_RATE_LIMIT", "").lower() in ("1", "true", "yes"):
            return True
        if ip in ("testclient",):
            return True

        now = time.monotonic()
        async with self._lock:
            # Prune stale IP entries every three minutes.
            if now - self._last_cleanup > 180:
                self._cleanup(now)

            history = self._requests[ip]
            cutoff = now - window_seconds
            # Retain requests within the sliding window.
            valid = [t for t in history if t > cutoff]
            if len(valid) >= max_requests:
                self._requests[ip] = valid
                return False

            valid.append(now)
            self._requests[ip] = valid
            return True

    def _cleanup(self, now: float):
        cutoff = now - 120
        for ip in list(self._requests.keys()):
            self._requests[ip] = [t for t in self._requests[ip] if t > cutoff]
            if not self._requests[ip]:
                del self._requests[ip]
        self._last_cleanup = now


rate_limiter = SimpleRateLimiter()


def get_client_ip(request: Request) -> str:
    """Resolve the client IP without trusting spoofed forwarding headers.

    Honor X-Forwarded-For, X-Real-IP, and CF-Connecting-IP only for requests
    from a trusted local or private-network proxy.
    """
    direct_ip = request.client.host if request.client else "unknown"

    # Trust loopback, private-network proxies, and testclient.
    is_trusted_proxy = (
        direct_ip in ("127.0.0.1", "::1", "localhost", "testclient", "unknown")
        or direct_ip.startswith("10.")
        or direct_ip.startswith("172.")
        or direct_ip.startswith("192.168.")
    )

    if is_trusted_proxy:
        # 1. Cloudflare header
        cf_ip = request.headers.get("cf-connecting-ip")
        if cf_ip:
            return cf_ip.strip()

        # The first X-Forwarded-For address identifies the original client.
        x_forwarded = request.headers.get("x-forwarded-for")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()

        # 3. X-Real-IP
        x_real = request.headers.get("x-real-ip")
        if x_real:
            return x_real.strip()

    # Fall back to the direct socket address.
    return direct_ip


async def check_rate_limit(request: Request, max_requests: int, window_seconds: int = 60):
    """Check the request limit and raise HTTP 429 when it is exceeded."""
    ip = get_client_ip(request)
    allowed = await rate_limiter.is_allowed(ip, max_requests, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Слишком много запросов с вашего IP-адреса. Пожалуйста, подождите минуту перед повторной попыткой.",
            headers={"Retry-After": str(window_seconds)}
        )
