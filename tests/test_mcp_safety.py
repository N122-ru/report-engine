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
    assert caps["file_path"] == ("standalone" if name == "headless" else False)
    assert caps["limits"] == {"image_bytes": 15 * 1024 * 1024, "images_count": 150, "markdown_bytes": 500 * 1024}
    assert set(caps["reference_resources"]) == {f"report://reference/{name}" for name in ("figures", "formulas", "tables", "style", "literals")}
    expected_resources = {
        "report://rules/gost732": "assets/SKILL.md",
        **{f"report://reference/{name}": f"assets/reference/{name}.md"
           for name in ("figures", "formulas", "tables", "style", "literals")},
    }
    resources = {resource["uri"]: resource for resource in caps["resources"]}
    assert set(resources) == set(expected_resources)
    for uri, path in expected_resources.items():
        data = open(path, "r", encoding="utf-8").read().strip().encode("utf-8")
        assert resources[uri] == {
            "uri": uri,
            "sha256": hashlib.sha256(data).hexdigest()[:12],
            "bytes": len(data),
        }


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


@pytest.mark.parametrize("include_file_path", [False, True])
def test_agent_onboarding_skips_questionnaire_and_keeps_one_shot_exit(include_file_path):
    from backend.app.engine.agent_resources import agent_onboarding_prompt

    text = agent_onboarding_prompt("TestClient", include_file_path=include_file_path)

    assert "максимум один короткий вопрос" in text.lower()
    assert "только если" in text.lower()
    assert "работа с этим сервером разовая или постоянная?" in text
    assert "постоянная или неизвестно" in text.lower()
    assert "без дополнительных вопросов" in text
    assert "Если задача one-shot, памятку вовсе не создавай" in text
    assert "заверши onboarding" in text
    for obsolete in ("4 вопроса", "Кто вы", "Где лежат исходники", "субагент", "после ответов пользователя"):
        assert obsolete not in text


@pytest.mark.parametrize("include_file_path", [False, True])
def test_agent_onboarding_teaches_and_maintains_client_optimizations(include_file_path):
    from backend.app.engine.agent_resources import agent_onboarding_prompt

    text = agent_onboarding_prompt("TestClient", include_file_path=include_file_path)
    assert "### Клиентские оптимизации\n" in text
    optimizations = text.split("### Клиентские оптимизации\n", 1)[1].split("### Правило приоритета", 1)[0]

    assert "чеклиста окружения и своего опыта" in optimizations
    assert "file_path" in optimizations
    assert "на одной машине с сервером" in optimizations
    assert "standalone" in optimizations
    assert "get_capabilities" in optimizations
    assert "base64" in optimizations
    assert "байты скриптом, не руками" in optimizations
    assert "Не кодируй большие файлы по памяти частями" in optimizations
    assert "batch вместо серий" in optimizations
    assert "digest вместо полного state" in optimizations
    assert "operation_id на мутациях" in optimizations
    assert "ядро правил -> правки -> lint_report -> экспорт" in optimizations
    assert "не использовать X - использовать Y" in optimizations
    assert "чем кодировать изображения на этой машине, какие пути допустимы" in optimizations
    assert "После каждой сессии работы с сервером дополняй" in optimizations
    assert "что сработало, что сломалось" in optimizations
    assert "не трогая серверный manifest-блок" in optimizations
    assert "Клиентские шорткаты" not in text


@pytest.mark.anyio
async def test_layered_resources_and_core_prompt_in_both_transports(transport):
    from pathlib import Path
    import anyio
    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams
    from backend.app.headless import _make_server

    name, _, _, _, report, client, token = transport
    core = Path("assets/SKILL.md").read_text(encoding="utf-8").strip()
    assert "agent_onboarding" in core
    assert "Клиентские оптимизации" in core
    assert "после каждой сессии" in core
    assert "задай его вопросы" not in core
    expected = {f"report://reference/{name}": Path(f"assets/reference/{name}.md").read_text(encoding="utf-8").strip()
                for name in ("figures", "formulas", "tables", "style", "literals")}

    def assert_initialize_instructions(instructions):
        assert instructions
        assert len(instructions) <= 800
        assert "agent_onboarding" in instructions
        assert "report://rules/gost732" in instructions
        assert "one-shot" in instructions
        assert "Клиентские оптимизации" in instructions
        assert "после каждой сессии" in instructions
        assert "Задай пользователю вопросы" not in instructions

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

        prompts = await request("prompts/list", {})
        assert {item["name"] for item in prompts["prompts"]} >= {"write_report", "agent_onboarding"}
        onboarding = await request("prompts/get", {
            "name": "agent_onboarding",
            "arguments": {"client_agent": "Hermes", "notes": "Локальный профиль клиента"},
        })
        onboarding_text = onboarding["messages"][0]["content"]["text"]
        assert "Hermes" in onboarding_text
        assert "максимум один короткий вопрос" in onboarding_text.lower()
        assert "4 вопроса" not in onboarding_text
        assert "Локальный профиль клиента" in onboarding_text
        assert "READ-ONLY" in onboarding_text
        assert "get_capabilities" in onboarding_text
        assert "transport" in onboarding_text
        assert "limits" in onboarding_text
        assert "file_path" in onboarding_text
        assert "tools_diff" in onboarding_text
        assert "resources/list" in onboarding_text
        assert "не пиши памятку" in onboarding_text.lower()
        assert "## Локальная памятка агента" in onboarding_text
        assert "skill_id: report-engine" in onboarding_text
        assert "contract_version:" in onboarding_text
        assert "sha256:" in onboarding_text
        assert "created_at:" in onboarding_text
        assert "### Клиентские оптимизации" in onboarding_text
        assert "серверный блок заменяется целиком" in onboarding_text.lower()
        assert "памятку вовсе не создавай" in onboarding_text.lower()
        assert "report://rules/gost732" in onboarding_text
        assert "ядро >" in onboarding_text
        assert "не переопределяет серверные правила" in onboarding_text
        assert "локальный скилл — кэш: сверяй версии с get_capabilities" in onboarding_text
        assert "не хранит" in onboarding_text
        assert "file_path" in onboarding_text
        assert "base64" in onboarding_text
        assert "После каждой сессии работы с сервером дополняй" in onboarding_text

    if name == "live":
        initialized = client.post(f"/api/mcp/messages?token={token}", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
        }).json()
        assert_initialize_instructions(initialized["result"]["instructions"])

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
                    initialized = await session.initialize()
                    assert_initialize_instructions(initialized.instructions)
                    async def request(method, params):
                        if method == "resources/list":
                            result = await session.list_resources()
                        elif method == "resources/read":
                            result = await session.read_resource(params["uri"])
                        elif method == "prompts/list":
                            result = await session.list_prompts()
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


def test_snapshot_id_is_atomic_and_replaces_legacy_revision_arguments(transport):
    _, call, write, _, _, _, _ = transport
    _, initial = call("get_report_state")
    assert initial["snapshot_id"]
    write("Исходный текст.")
    _, current = call("get_report_state")
    assert current["snapshot_id"] != initial["snapshot_id"]
    if transport[0] == "headless":
        arguments = {"fields": {"work_theme": "Тема"}, "expected_snapshot_id": current["snapshot_id"]}
    else:
        arguments = {"work_theme": "Тема", "expected_snapshot_id": current["snapshot_id"]}
    assert not call("update_meta", **arguments)[0]
    _, changed = call("get_report_state")
    assert changed["snapshot_id"] != current["snapshot_id"]
    before = changed["markdown_content"]
    error, result = call("append_or_update_section", section_heading="# Вывод",
                         section_content="Не должно сохраниться.",
                         expected_snapshot_id=current["snapshot_id"])
    assert error
    assert "refresh_and_retry" in result
    _, after = call("get_report_state")
    assert after["markdown_content"] == before


def test_revision_conflicts_include_machine_readable_next_action(transport):
    _, call, _, _, _, _, _ = transport
    _, state = call("get_report_state")
    error, text = call("append_or_update_section", section_heading="# Вывод",
                       section_content="Текст.", expected_snapshot_id="stale")
    assert error
    payload = json.loads(text)
    assert payload["conflict"] is True
    assert payload["current"]["snapshot_id"] == state["snapshot_id"]
    assert payload["next_action"] == "refresh_and_retry"


def test_batch_stale_snapshot_is_rejected_before_any_call(transport):
    name, call, _, _, report, _, _ = transport
    _, before = call("get_report_state")
    error, result = call(
        "batch", expected_snapshot_id="stale", calls=[
            {"name": "update_meta", "arguments": {
                "work_theme": "Не должно примениться",
                "expected_snapshot_id": before["snapshot_id"],
            }},
        ],
    )
    assert error
    payload = json.loads(result)
    assert payload["conflict"] is True
    assert payload["current"]["snapshot_id"] == before["snapshot_id"]
    assert payload["next_action"] == "refresh_and_retry"
    assert call("get_report_state")[1]["metadata"] == before["metadata"]


def test_snapshot_only_mutations_are_advertised_and_dispatched(transport):
    name, call, _, export, _, client, token = transport
    if name == "live":
        schemas = {}
        cursor = None
        while True:
            params = {} if cursor is None else {"cursor": cursor}
            page = client.post(f"/api/mcp/messages?token={token}", json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": params,
            }).json()["result"]
            schemas.update({tool["name"]: tool["inputSchema"] for tool in page["tools"]})
            cursor = page.get("nextCursor")
            if cursor is None:
                break
    else:
        from backend.app.headless import _tools
        schemas = {tool.name: tool.input_schema for tool in _tools()}
    for tool_name in ("append_or_update_section", "update_meta", "export_report"):
        assert "expected_snapshot_id" not in schemas[tool_name]["required"]

    _, state = call("get_report_state")
    assert not call("append_or_update_section", section_heading="# Вывод",
                    section_content="Снимок применяется.",
                    expected_snapshot_id=state["snapshot_id"])[0]
    _, state = call("get_report_state")
    metadata = {"fields": {"work_theme": "Снимок"}} if name == "headless" else {"work_theme": "Снимок"}
    assert not call("update_meta", expected_snapshot_id=state["snapshot_id"], **metadata)[0]
    assert not call("lint_report")[0]
    _, state = call("get_report_state")
    error, result = export(expected_snapshot_id=state["snapshot_id"])
    assert not error, result


def test_operation_cache_bounds_results_and_operation_ids():
    from backend.app.engine.report_safety import OperationCache

    cache = OperationCache(limit=10, max_bytes=180)
    assert cache.store("first", {}, {"value": "a" * 100}) is None
    assert cache.store("second", {}, {"value": "b" * 100}) is None
    assert cache.lookup("first", {}) is None
    assert cache.lookup("second", {}) == {"value": "b" * 100}
    marker = cache.store("large", {}, {"value": "x" * (256 * 1024)})
    assert marker == {"cached": False, "reason": "result_too_large"}
    assert cache.lookup("large", {}) is None
    with pytest.raises(ValueError, match="128"):
        cache.store("x" * 129, {}, {"value": "small"})


def test_batch_error_is_a_string_with_optional_structured_detail(transport):
    _, call, _, _, _, _, _ = transport
    error, result = call("batch", calls=[{"name": "unknown", "arguments": {}}])
    assert not error
    assert isinstance(result[0]["error"], str)


def test_headless_export_response_contains_all_revisions(tmp_path):
    report = HeadlessReport(tmp_path)
    report.create_report()
    report.lint_report()
    state = report.get_report_state()
    result = report.export_report(
        "revisions.docx", state["revision"], state["meta_revision"], state["image_revision"],
    )
    assert {key: result[key] for key in ("revision", "meta_revision", "image_revision", "snapshot_id")} == {
        key: state[key] for key in ("revision", "meta_revision", "image_revision", "snapshot_id")
    }


def test_operation_id_retries_are_cached_without_reapplying(transport):
    _, call, _, _, _, _, _ = transport
    _, state = call("get_report_state")
    if transport[0] == "headless":
        arguments = {"fields": {"work_theme": "Повторяемая тема"},
                     "expected_meta_revision": state["meta_revision"], "operation_id": "op-meta-1"}
    else:
        arguments = {"work_theme": "Повторяемая тема",
                     "expected_meta_revision": state["meta_revision"], "operation_id": "op-meta-1"}
    error, first = call("update_meta", **arguments)
    assert not error
    _, after_first = call("get_report_state")
    error, second = call("update_meta", **arguments)
    assert not error
    assert second == first
    _, after_retry = call("get_report_state")
    assert after_retry["snapshot_id"] == after_first["snapshot_id"]
    if transport[0] == "headless":
        different = {"fields": {"work_theme": "Другая тема"}, **{
            key: arguments[key] for key in ("operation_id",)
        }}
    else:
        different = {"work_theme": "Другая тема", "operation_id": arguments["operation_id"]}
    assert call("update_meta", **different)[0]


def test_batch_references_chain_previous_results_in_headless(tmp_path):
    from backend.app.headless import _dispatch_tool
    report = __import__("backend.app.engine.headless_report", fromlist=["HeadlessReport"]).HeadlessReport(tmp_path)
    result = _dispatch_tool(report, "batch", {"calls": [
        {"name": "create_report", "arguments": {}},
        {"name": "update_meta", "arguments": {
            "fields": {"work_theme": "Проверка ссылок"},
            "expected_meta_revision": "$0.meta_revision",
        }},
        {"name": "get_report_state", "arguments": {}},
    ]})
    assert not result.is_error
    payload = json.loads(result.content[0].text)
    assert all(item["ok"] for item in payload)
    assert payload[2]["result"]["metadata"]["work_theme"] == "Проверка ссылок"

    broken = _dispatch_tool(report, "batch", {"calls": [
        {"name": "get_report_state", "arguments": {}},
        {"name": "update_meta", "arguments": {
            "fields": {"work_theme": "Не применено"}, "expected_meta_revision": "$0.no_such_field",
        }},
    ]})
    broken_payload = json.loads(broken.content[0].text)
    assert broken_payload[1]["ok"] is False
    assert "Ссылка" in broken_payload[1]["error"]


def test_operation_ids_do_not_leak_between_headless_reports(tmp_path):
    from backend.app.engine.headless_report import HeadlessReport
    from backend.app.headless import _dispatch_tool

    # The output directories must exist before a headless report is constructed.
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = HeadlessReport(first_dir)
    second = HeadlessReport(second_dir)
    for report in (first, second):
        result = _dispatch_tool(report, "create_report", {"operation_id": "create-once"})
        assert not result.is_error
        assert report.metadata is not None


def test_live_and_headless_share_the_common_tool_names(transport):
    from backend.app.headless import _tools
    name, _, _, _, _, client, token = transport
    headless_names = {tool.name for tool in _tools()}
    if name == "live":
        from backend.app.engine.mcp_router import MCP_LIVE_TOOLS
        live_names = {tool["name"] for tool in MCP_LIVE_TOOLS}
        capabilities = client.post(f"/api/mcp/messages?token={token}", json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "get_capabilities", "arguments": {}},
        }).json()["result"]
        capabilities = json.loads(capabilities["content"][0]["text"])
    else:
        live_names = {"batch", "list_images", "get_image", "get_images", "upload_image",
                      "upload_images", "get_report_state", "append_or_update_section",
                      "update_meta", "delete_image", "lint_report", "autofix_typography",
                      "import_profile", "get_capabilities", "review_snapshot", "export_report"}
        error, capabilities = transport[1]("get_capabilities")
        assert not error
    common = {"batch", "list_images", "get_image", "get_images", "upload_image",
              "upload_images", "get_report_state", "append_or_update_section", "update_meta",
              "delete_image", "lint_report", "autofix_typography", "import_profile",
              "get_capabilities", "review_snapshot", "export_report"}
    assert common <= live_names
    assert common <= headless_names
    assert isinstance(capabilities["tools_diff"], list)
