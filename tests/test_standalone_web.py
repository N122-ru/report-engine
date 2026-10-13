from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.standalone_web import (
    LOOPBACK_HOST,
    LocalOnlyApp,
    ensure_frontend_dist,
    ensure_port_available,
    is_local_origin,
    is_local_host,
    validate_port,
)
from backend.app.engine.pdf_converter import pdf_export_enabled


async def ok_app(scope, receive, send):
    if scope["type"] != "http":
        return
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


@pytest.mark.parametrize("host", ["localhost", "localhost:8000", "127.0.0.1", "[::1]:8000"])
def test_loopback_hosts_are_allowed(host):
    assert is_local_host(host, 8000)


@pytest.mark.parametrize("host", ["example.com", "192.168.1.5:8000", "localhost:5173"])
def test_non_loopback_hosts_are_rejected(host):
    assert not is_local_host(host, 8000)


@pytest.mark.parametrize("origin", [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://[::1]:8000",
])
def test_loopback_origins_are_allowed(origin):
    assert is_local_origin(origin, 8000)


@pytest.mark.parametrize("origin", ["https://example.com", "http://localhost:5173", "null"])
def test_non_loopback_origins_are_rejected(origin):
    assert not is_local_origin(origin, 8000)


def test_local_only_app_rejects_foreign_host_and_origin():
    client = TestClient(LocalOnlyApp(ok_app, port=8000))
    assert client.get("/", headers={"host": "example.com"}).status_code == 403
    assert client.get("/", headers={"origin": "https://example.com"}).status_code == 403
    response = client.get("/", headers={"host": "localhost:8000", "origin": "http://localhost:8000"})
    assert response.status_code == 200
    assert response.text == "ok"


def test_frontend_dist_must_contain_index(tmp_path):
    with pytest.raises(RuntimeError, match="frontend/dist/index.html"):
        ensure_frontend_dist(tmp_path / "dist")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    assert ensure_frontend_dist(dist) == dist.resolve()


def test_standalone_contract_uses_loopback_host():
    assert LOOPBACK_HOST == "127.0.0.1"


@pytest.mark.parametrize("port", [0, -1, 65536, True, "8000"])
def test_invalid_ports_are_rejected(port):
    with pytest.raises(ValueError, match="Порт"):
        validate_port(port)


def test_occupied_port_is_rejected():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((LOOPBACK_HOST, 0))
        port = sock.getsockname()[1]
        with pytest.raises(RuntimeError, match="занят"):
            ensure_port_available(port)


def test_pdf_export_can_be_disabled_by_runtime_configuration(monkeypatch):
    monkeypatch.setenv("REPORT_ENGINE_DISABLE_PDF", "1")
    assert not pdf_export_enabled()
