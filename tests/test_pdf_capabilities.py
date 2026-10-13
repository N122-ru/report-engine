import os
import sys

sys.path.insert(0, os.path.abspath("backend"))

from fastapi.testclient import TestClient

from app import main as main_module
from app.main import app


def test_capabilities_endpoint_exposes_pdf_runtime_status():
    response = TestClient(app).get("/api/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["pdf_export"], bool)
    assert payload["pdf_converter"] in {None, "office", "docbuilder"}


def test_pdf_generation_is_explicitly_unavailable_without_converter(monkeypatch):
    monkeypatch.setattr(main_module, "pdf_export_status", lambda: {
        "pdf_export": False,
        "pdf_converter": None,
    })

    response = TestClient(app).post(
        "/api/generate",
        data={"meta": "{}", "content": "Текст", "format": "pdf"},
    )

    assert response.status_code == 501
    assert "PDF недоступен" in response.json()["detail"]
