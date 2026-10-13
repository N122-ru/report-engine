"""Loopback-only launcher for the browser-based standalone distribution."""

import argparse
import socket
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any, Awaitable, Callable

import uvicorn


LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


def _parsed_host(value: str):
    raw = (value or "").strip()
    if not raw or "@" in raw or "/" in raw:
        return None
    try:
        parsed = urlsplit(f"//{raw}")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            return None
        hostname = parsed.hostname
        if not hostname:
            return None
        port = parsed.port
    except ValueError:
        return None
    return hostname.casefold(), port


def is_local_host(value: str, port: int) -> bool:
    parsed = _parsed_host(value)
    return bool(parsed and parsed[0] in LOCAL_HOSTNAMES and (parsed[1] is None or parsed[1] == port))


def is_local_origin(value: str, port: int) -> bool:
    raw = (value or "").strip()
    if raw == "null":
        return False
    try:
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return False
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            return False
    except ValueError:
        return False
    return is_local_host(parsed.netloc, port)


def ensure_frontend_dist(path: Path = FRONTEND_DIST) -> Path:
    """Require a prebuilt SPA and never build or download it at runtime."""
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("Не найдена готовая сборка frontend/dist/index.html") from exc
    if not resolved.is_dir() or not (resolved / "index.html").is_file():
        raise RuntimeError("Не найдена готовая сборка frontend/dist/index.html")
    return resolved


def validate_port(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError("Порт должен быть целым числом от 1 до 65535")
    return value


def ensure_port_available(port: int) -> None:
    validate_port(port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((LOOPBACK_HOST, port))
        except OSError as exc:
            raise RuntimeError(f"Порт {port} уже занят или недоступен") from exc


def _header(scope: dict[str, Any], name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return ""


class LocalOnlyApp:
    """Reject non-loopback HTTP metadata before it reaches the FastAPI app."""

    def __init__(self, app: Callable[..., Awaitable[Any]], port: int):
        self.app = app
        self.port = validate_port(port)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            host = _header(scope, b"host")
            origin = _header(scope, b"origin")
            if not is_local_host(host, self.port) or (origin and not is_local_origin(origin, self.port)):
                body = '{"detail":"Разрешены только локальные запросы"}'.encode("utf-8")
                await send({
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"cache-control", b"no-store"),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def create_application(port: int = DEFAULT_PORT) -> LocalOnlyApp:
    """Validate the distribution before importing the HTTP application."""
    port = validate_port(port)
    ensure_frontend_dist()
    from .main import app

    return LocalOnlyApp(app, port)


def run(port: int = DEFAULT_PORT) -> None:
    port = validate_port(port)
    application = create_application(port)
    ensure_port_available(port)
    print(f"Веб-интерфейс: http://{LOOPBACK_HOST}:{port}", flush=True)
    server = uvicorn.Server(uvicorn.Config(
        application,
        host=LOOPBACK_HOST,
        port=port,
        log_level="info",
        proxy_headers=False,
        access_log=True,
    ))
    server.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Report Engine on the local loopback interface")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    try:
        run(args.port)
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
