"""Exercise additive safety contracts through both MCP transports."""

import base64
import hashlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath("backend"))

import pytest
from docx import Document
from fastapi.testclient import TestClient

from backend.app.engine.headless_report import HeadlessReport
from backend.app.headless import _dispatch_tool
from app.main import app


@pytest.fixture(params=["headless", "live"])
def transport(request, tmp_path, monkeypatch):
    """Provide a fresh report and the actual transport's tool boundary."""
    monkeypatch.setenv("REPORT_ENGINE_DISABLE_PDF", "1")
    client = TestClient(app)
    report = HeadlessReport(tmp_path)
    if request.param == "headless":
        report.create_report()
        token = None
    else:
        token = client.get("/api/session/init").json()["token"]

    def call(name, **arguments):
        if request.param == "headless":
            result = _dispatch_tool(report, name, arguments)
            error = result.is_error
            text = result.content[0].text
        else:
            response = client.post(f"/api/mcp/messages?token={token}", json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            })
            assert response.status_code == 200
            result = response.json()["result"]
            error = result["isError"]
            text = result["content"][0]["text"]
        return error, text if error else json.loads(text)

    def write(text):
        _, state = call("get_report_state")
        error, result = call("append_or_update_section", section_heading="# Ход работы",
                             section_content=text, expected_revision=state["revision"])
        assert not error, result

    def export(**extra):
        _, state = call("get_report_state")
        return call("export_report", filename="report.docx", **{
            f"expected_{key}": state[key] for key in ("revision", "meta_revision", "image_revision")
        }, **extra)

    return request.param, call, write, export, report, client, token


@pytest.mark.parametrize("text, kind", [
    ("На скриншоте данной информации нет.", "placeholder"),
    ("Данных нет.", "placeholder"),
    ("Информация отсутствует.", "placeholder"),
    ("Результат сохранён в /home/student/draft/output.png.", "internal_path"),
    ("Материалы находятся в /data/reports/one.", "internal_path"),
    (r"Файл лежит в C:\Users\Student\draft.png.", "internal_path"),
    ("Прикреплён файл с заданием.", "preparation_note"),
    ("Как указано в задании в файле, выполнена настройка.", "preparation_note"),
    ("На предоставленном скриншоте показана настройка.", "preparation_note"),
    ("![Схема](missing.png)", "missing_image"),
])
def test_lint_guards_find_unresolved_items(transport, text, kind):
    _, call, write, _, _, _, _ = transport
    write(text)
    error, lint = call("lint_report")
    assert not error
    items = [item for item in lint["unresolved_items"] if item["kind"] == kind]
    assert items
    assert all(set(item) == {"id", "kind", "message", "location"} for item in items)
    assert all(item["id"] and item["location"] for item in items)
    assert bool(lint["export_blockers"]) == (kind in {"placeholder", "missing_image"})


@pytest.mark.parametrize("text", [
    "На рисунке 4.2 приведена схема стенда.",
    "Программа создаёт скриншот экрана для анализа интерфейса.",
    "```text\nДанных нет. /home/student/test\n![Схема](missing.png)\n```",
    "~~~text\nИнформация отсутствует.\n![Схема](missing.png)\n~~~",
    "Выполнена команда `echo 'данных нет'`.",
])
def test_lint_guards_preserve_figure_references_and_literals(transport, text):
    _, call, write, _, _, _, _ = transport
    write(text)
    error, lint = call("lint_report")
    assert not error
    assert lint["unresolved_items"] == []
    assert lint["export_blockers"] == []


@pytest.mark.parametrize("blocked", [False, "placeholder", "missing_image"])
def test_export_blockers_require_explicit_confirmation(transport, blocked):
    name, call, write, export, report, _, _ = transport
    write({"placeholder": "Данных нет.", "missing_image": "![Схема](missing.png)"}.get(blocked, "Выполнено исследование."))
    error, lint = call("lint_report")
    assert not error
    error, result = export()
    assert error == bool(blocked)
    if blocked:
        assert blocked in result
        error, result = export(confirm_blocked_export="true")
        assert error
        error, result = export(confirm_blocked_export=True)
        assert not error, result
    data = (report.output_dir / "report.docx").read_bytes() if name == "headless" else base64.b64decode(result["base64_data"])
    assert result["size_bytes"] == len(data)
    assert result["sha256"] == hashlib.sha256(data).hexdigest()
    assert "Ход работы" in "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)


@pytest.mark.parametrize("mutation", ["text", "meta", "image"])
def test_export_requires_lint_after_every_mutation(transport, mutation):
    name, call, write, export, _, _, _ = transport
    write("Выполнено исследование.")
    error, result = export(confirm_blocked_export=True)
    assert error and "сначала проверь отчёт" in result.lower()
    assert not call("lint_report")[0]
    _, state = call("get_report_state")
    assert state["verify_state"] == {"lint_after_last_change": True, "export_allowed": True}
    if mutation == "text":
        write("Получен результат.")
    elif mutation == "meta":
        args = {"fields": {"work_theme": "Новая тема"}} if name == "headless" else {"work_theme": "Новая тема"}
        assert not call("update_meta", expected_meta_revision=state["meta_revision"], **args)[0]
    else:
        args = {"expected_image_revision": state["image_revision"]} if name == "headless" else {"expected_revision": state["revision"]}
        assert not call("upload_image", filename="unused.png",
                        base64_data=base64.b64encode(b"\x89PNG\r\n\x1a\n").decode(), **args)[0]
    _, state = call("get_report_state")
    assert state["verify_state"] == {"lint_after_last_change": False, "export_allowed": False}
    assert export(confirm_blocked_export=True)[0]
    assert not call("lint_report")[0]
    error, result = export()
    assert not error, result


def test_review_snapshot_is_read_only_and_digest_is_compact(transport):
    _, call, write, export, _, _, _ = transport
    write("На рисунке 1 приведена схема.\n\n![Схема](missing.png)")
    _, before = call("get_report_state")
    error, snapshot = call("review_snapshot")
    assert not error
    assert snapshot["markdown_content"] == before["markdown_content"]
    assert snapshot["metadata"] == before["metadata"]
    assert "base64" not in json.dumps(snapshot)
    assert "lint" in snapshot and "images" in snapshot
    assert snapshot["lint"]["export_blockers"]
    _, after = call("get_report_state")
    assert {key: value for key, value in before.items() if key != "last_active"} == {
        key: value for key, value in after.items() if key != "last_active"
    }
    assert export()[0]
    _, digest = call("get_report_state", detail="digest")
    assert "markdown_content" not in digest and "metadata" not in digest
    assert digest["sections"][0]["heading"] == "# Ход работы"
    assert digest["sections"][0]["word_count"] > 0
    assert digest["image_refs"][0]["status"] == "missing"
    assert all(digest[key] == before[key] for key in ("revision", "meta_revision", "image_revision", "verify_state"))


def test_snapshot_image_manifest_and_digest_attachment_status(transport):
    name, call, write, _, _, _, _ = transport
    _, state = call("get_report_state")
    data = b"\x89PNG\r\n\x1a\n"
    args = {"expected_image_revision": state["image_revision"]} if name == "headless" else {"expected_revision": state["revision"]}
    assert not call("upload_image", filename="image.png", base64_data=base64.b64encode(data).decode(), **args)[0]
    write("![Схема](image.png)")
    _, snapshot = call("review_snapshot")
    image = snapshot["images"][0]
    assert image["filename"] == "image.png"
    assert image["size_bytes"] == len(data)
    assert image["sha256"] == hashlib.sha256(data).hexdigest()
    assert image["is_in_report"] is True
    assert not {"base64_data", "data", "blob"} & image.keys()
    _, digest = call("get_report_state", detail="digest")
    assert digest["image_refs"][0]["status"] == "attached"


def test_capabilities_advertise_runtime_and_limits(transport):
    name, call, _, _, _, _, _ = transport
    error, caps = call("get_capabilities")
    assert not error
    assert caps["transport"] == name
    assert caps["contract_version"]
    assert caps["pdf_export"] is False
    assert caps["file_path"] is True
    assert caps["limits"] == {"image_bytes": 15 * 1024 * 1024, "images_count": 150, "markdown_bytes": 500 * 1024}
    assert set(caps["reference_resources"]) == {f"report://reference/{name}" for name in ("figures", "formulas", "tables", "style", "literals")}


def test_noop_metadata_retains_verification_and_invalid_detail_is_rejected(transport):
    name, call, write, _, _, _, _ = transport
    write("Выполнено исследование.")
    _, state = call("get_report_state")
    patch = {"work_theme": "Тема"}
    args = {"fields": patch} if name == "headless" else patch
    assert not call("update_meta", expected_meta_revision=state["meta_revision"], **args)[0]
    assert not call("lint_report")[0]
    _, state = call("get_report_state")
    assert not call("update_meta", expected_meta_revision=state["meta_revision"], **args)[0]
    _, after = call("get_report_state")
    assert after["verify_state"] == state["verify_state"]
    assert after["meta_revision"] == state["meta_revision"]
    assert call("get_report_state", detail="unknown")[0]


def test_confirmation_is_not_sticky_and_stale_revisions_fail(transport):
    _, call, write, export, _, _, _ = transport
    write("Данных нет.")
    assert not call("lint_report")[0]
    assert not export(confirm_blocked_export=True)[0]
    error, result = export()
    assert error and "placeholder" in result
    _, state = call("get_report_state")
    error, result = call("export_report", filename="other.docx", expected_revision="stale",
                         expected_meta_revision=state["meta_revision"], expected_image_revision=state["image_revision"],
                         confirm_blocked_export=True)
    assert error and "верси" in result.lower()


@pytest.mark.anyio
async def test_layered_resources_and_core_prompt_in_both_transports(transport):
    from pathlib import Path
    import anyio
    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams
    from backend.app.headless import _make_server

    name, _, _, _, report, client, token = transport
    core = Path("assets/SKILL.md").read_text(encoding="utf-8").strip()
    expected = {f"report://reference/{name}": Path(f"assets/reference/{name}.md").read_text(encoding="utf-8").strip()
                for name in ("figures", "formulas", "tables", "style", "literals")}

    async def verify(request):
        resources = await request("resources/list", {})
        assert set(expected) <= {str(item["uri"]) for item in resources["resources"]}
        for uri, text in expected.items():
            response = await request("resources/read", {"uri": uri})
            assert response["contents"][0]["text"] == text
        response = await request("resources/read", {"uri": "report://rules/gost732"})
        assert response["contents"][0]["text"] == core
        prompt = await request("prompts/get", {"name": "write_report", "arguments": {"task": "Проверка"}})
        text = prompt["messages"][0]["content"]["text"]
        assert core in text
        assert all(reference not in text for reference in expected.values())
        assert all(uri in text for uri in expected)

    if name == "live":
        async def request(method, params):
            response = client.post(f"/api/mcp/messages?token={token}", json={
                "jsonrpc": "2.0", "id": 2, "method": method, "params": params,
            }).json()
            assert "error" not in response, response
            return response["result"]
        await verify(request)
        rejected = client.post(f"/api/mcp/messages?token={token}", json={
            "jsonrpc": "2.0", "id": 2, "method": "resources/read",
            "params": {"uri": "report://reference/../../SKILL.md"},
        }).json()
        assert "error" in rejected
    else:
        server = _make_server(report)
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            async with anyio.create_task_group() as group:
                async def run():
                    await server.run(*server_streams, server.create_initialization_options())
                group.start_soon(run)
                async with ClientSession(*client_streams) as session:
                    await session.initialize()
                    async def request(method, params):
                        if method == "resources/list":
                            result = await session.list_resources()
                        elif method == "resources/read":
                            result = await session.read_resource(params["uri"])
                        else:
                            result = await session.get_prompt(params["name"], params["arguments"])
                        return result.model_dump(mode="json", by_alias=True)
                    await verify(request)
                    with pytest.raises(Exception, match="Справочник не найден"):
                        await session.read_resource("report://reference/../../SKILL.md")
                group.cancel_scope.cancel()


def test_live_lint_of_other_markdown_does_not_grant_export():
    client = TestClient(app)
    token = client.get("/api/session/init").json()["token"]
    client.post(f"/api/session/{token}/sync", json={"content": "Данных нет."})
    response = client.post(f"/api/mcp/messages?token={token}", json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "lint_report", "arguments": {"markdown_content": "Выполнено исследование."}},
    }).json()["result"]
    assert response["isError"] is False
    state = client.post(f"/api/mcp/messages?token={token}", json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_report_state", "arguments": {}},
    }).json()["result"]
    assert json.loads(state["content"][0]["text"])["verify_state"]["lint_after_last_change"] is False


def test_live_rollback_and_browser_mutations_invalidate_lint():
    client = TestClient(app)
    token = client.get("/api/session/init").json()["token"]

    def call(name, **args):
        result = client.post(f"/api/mcp/messages?token={token}", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }).json()["result"]
        assert not result["isError"], result
        return json.loads(result["content"][0]["text"])

    client.post(f"/api/session/{token}/sync", json={"content": "Исходный текст."})
    call("lint_report")
    original = call("get_report_state")
    changed = call("patch_text", find="Исходный", replace="Новый", expected_revision=original["revision"])
    call("rollback_last_edit", expected_revision=changed["revision"])
    restored = call("get_report_state")
    assert restored["revision"] == original["revision"]
    assert not restored["verify_state"]["lint_after_last_change"]
    for payload in ({"content": "Другой текст."}, {"meta": {"work_theme": "Другая тема"}}):
        call("lint_report")
        assert client.post(f"/api/session/{token}/sync", json=payload).status_code == 200
        assert not call("get_report_state")["verify_state"]["lint_after_last_change"]
    call("lint_report")
    assert client.post(f"/api/session/{token}/images", files={"files": ("unused.png", b"image", "image/png")}).status_code == 200
    assert not call("get_report_state")["verify_state"]["lint_after_last_change"]
    call("lint_report")
    assert client.delete(f"/api/session/{token}/images/unused.png").status_code == 200
    assert not call("get_report_state")["verify_state"]["lint_after_last_change"]
