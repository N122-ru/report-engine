import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath("backend"))

from fastapi.testclient import TestClient

from app.engine import update_checker
from app.main import app
from app.version import APP_VERSION


class FakeResponse:
    def __init__(self, payload: object):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int = -1):
        return self.payload


def test_default_repository_is_used_when_update_settings_are_absent(monkeypatch):
    monkeypatch.delenv("REPORT_ENGINE_UPDATE_URL", raising=False)
    monkeypatch.delenv("REPORT_ENGINE_UPDATE_REPOSITORY", raising=False)
    requests = []
    monkeypatch.setattr(
        update_checker,
        "urlopen",
        lambda request, timeout: (requests.append(request.full_url) or FakeResponse({
            "tag_name": "v0.1.0",
            "html_url": "https://github.com/N122-ru/report-engine/releases/tag/v0.1.0",
        })),
    )

    result = update_checker.get_update_info()

    assert requests == [
        "https://api.github.com/repos/N122-ru/report-engine/releases/latest",
    ]
    assert result["status"] == "current"


def setup_function():
    update_checker.reset_update_cache()


def test_version_endpoint_exposes_canonical_version(monkeypatch):
    monkeypatch.delenv("REPORT_ENGINE_UPDATE_URL", raising=False)
    monkeypatch.delenv("REPORT_ENGINE_UPDATE_REPOSITORY", raising=False)
    monkeypatch.setattr(update_checker, "urlopen", lambda _request, timeout: (_ for _ in ()).throw(OSError()))

    response = TestClient(app).get("/api/version")

    assert response.status_code == 200
    assert response.json() == {
        "version": APP_VERSION,
        "update": {
            "status": "unavailable",
            "latest_version": None,
            "release_url": None,
        },
    }


def test_update_checker_accepts_github_release_payload(monkeypatch):
    feed_url = "https://api.github.com/repos/example/report-engine/releases/latest"
    monkeypatch.setenv("REPORT_ENGINE_UPDATE_URL", feed_url)
    monkeypatch.setattr(
        update_checker,
        "urlopen",
        lambda _request, timeout: FakeResponse({
            "tag_name": "v99.1.0",
            "html_url": "https://github.com/example/report-engine/releases/tag/v99.1.0",
        }),
    )

    result = update_checker.get_update_info()

    assert result == {
        "status": "available",
        "latest_version": "99.1.0",
        "release_url": "https://github.com/example/report-engine/releases/tag/v99.1.0",
    }


def test_update_checker_fails_closed_for_invalid_remote_data(monkeypatch):
    monkeypatch.setenv("REPORT_ENGINE_UPDATE_URL", "https://updates.example.test/latest")
    monkeypatch.setattr(
        update_checker,
        "urlopen",
        lambda _request, timeout: FakeResponse({"tag_name": "not-a-version"}),
    )

    result = update_checker.get_update_info()

    assert result == {
        "status": "unavailable",
        "latest_version": None,
        "release_url": None,
    }


def test_semver_comparison_handles_prereleases():
    assert update_checker.compare_versions("1.2.0", "1.2.0") == 0
    assert update_checker.compare_versions("1.2.0", "1.3.0") == -1
    assert update_checker.compare_versions("1.2.0-rc.1", "1.2.0") == -1


def test_frontend_package_metadata_matches_canonical_version():
    root = Path(__file__).resolve().parents[1]
    package = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    lockfile = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))

    assert package["version"] == APP_VERSION
    assert lockfile["version"] == APP_VERSION
    assert lockfile["packages"][""]["version"] == APP_VERSION
