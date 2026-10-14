import io
import base64
import json
import subprocess
import sys

import pytest
from docx import Document

from backend.app.engine.headless_report import HeadlessReport


def call_tool(report, name, arguments):
    from backend.app.headless import _dispatch_tool

    result = _dispatch_tool(report, name, arguments)
    return result, json.loads(result.content[0].text) if not result.is_error else None


@pytest.fixture
def report(tmp_path):
    return HeadlessReport(tmp_path)


def add_section(report, heading, content):
    return report.append_or_update_section(
        heading, content, report.get_report_state()["revision"]
    )


def export(report, filename):
    report.lint_report()
    state = report.get_report_state()
    return report.export_report(
        filename, state["revision"], state["meta_revision"], state["image_revision"]
    )


def test_headless_core_does_not_import_fastapi():
    result = subprocess.run(
        [sys.executable, "-c", "import sys; sys.modules['fastapi'] = None; "
         "from backend.app.engine.headless_report import HeadlessReport"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_creation_keeps_state_in_memory_and_cannot_reset(report, tmp_path):
    created = report.create_report({"work_theme": "Проверка"})
    assert created["metadata"]["work_theme"] == "Проверка"
    assert created["markdown_content"] == ""
    add_section(report, "# Цель работы", "Исследование.")
    before = report.get_report_state()
    with pytest.raises(ValueError, match="уже создан"):
        report.create_report()
    assert report.get_report_state() == before
    assert list(tmp_path.iterdir()) == []


def test_metadata_update_preserves_other_fields_and_checks_revision(report):
    state = report.create_report({"city": "Москва"})
    updated = report.update_meta({"work_theme": "Тема"}, state["meta_revision"])
    assert updated["meta_revision"] != state["meta_revision"]
    assert report.get_report_state()["metadata"]["city"] == "Москва"
    before = report.get_report_state()
    with pytest.raises(ValueError, match="верси"):
        report.update_meta({"city": "Самара"}, state["meta_revision"])
    assert report.get_report_state() == before


def test_headless_import_profile_accepts_object_and_requires_revision_for_existing_report(report):
    profile = {
        "format": "report-engine-profile",
        "version": 1,
        "subject": {
            "id": "subj_profile",
            "name": "Сетевые технологии",
            "institute": "Институт технологий",
            "department": "Кафедра сетей",
            "teachers": [{"fio": "И.И. Иванов", "role": "доцент"}],
            "custom_instructions": "Сохранять команды.",
            "last_work_number": 4,
        },
        "meta": {
            "university": "Учебный университет",
            "ministry": "Министерство образования",
            "logo_mode": "none",
            "city": "Москва",
            "institute": "Институт технологий",
            "department": "Кафедра сетей",
            "doc_type": "ОТЧЕТ",
            "work_type": "о выполнении лабораторной работы",
            "work_number": 5,
            "discipline": "Сетевые технологии",
            "students": [{"fio": "П.П. Петров", "group": "ИВТ-101"}],
            "teachers": [{"fio": "И.И. Иванов", "role": "доцент"}],
            "year": 2026,
        },
    }
    first = report.import_profile(profile)
    assert first["metadata"]["discipline"] == "Сетевые технологии"
    assert first["profile_subject"]["last_work_number"] == 4

    before = report.get_report_state()
    with pytest.raises(ValueError, match="meta_revision"):
        report.import_profile(profile)
    assert report.get_report_state() == before

    updated = report.import_profile(profile, before["meta_revision"])
    assert updated["meta_revision"] == report.get_report_state()["meta_revision"]


@pytest.mark.parametrize("metadata", [{"unknown": 1}, {"year": "bad"}])
def test_invalid_metadata_does_not_create_a_report(report, metadata):
    with pytest.raises(ValueError):
        report.create_report(metadata)
    assert report.create_report()["markdown_content"] == ""


@pytest.mark.parametrize("metadata", [
    {"logo_mode": "custom", "custom_logo": "/private/logo.png"},
    {"logo_mode": "custom", "custom_logo": "data:image/png;base64,AAAA"},
])
def test_prototype_rejects_custom_logo_side_effects(report, metadata):
    with pytest.raises(ValueError, match="логотип"):
        report.create_report(metadata)
    assert report.create_report()["markdown_content"] == ""


def test_section_replacement_uses_markdown_boundaries_and_keeps_neighbors(report):
    report.create_report()
    add_section(report, "# Цель работы", "Исследование.")
    add_section(report, "# Ход работы", "До правки.\n\n```python\n# Вывод\nprint(1)\n```")
    add_section(report, "# Вывод", "После исследования.")
    add_section(report, "# Ход работы", "После правки.")
    text = report.get_report_state()["markdown_content"]
    assert text.count("# Ход работы") == 1
    assert "До правки" not in text
    assert "# Цель работы\n\nИсследование." in text
    assert "# Вывод\n\nПосле исследования." in text


def test_stale_text_write_is_rejected_without_state_change(report):
    state = report.create_report()
    add_section(report, "# Цель работы", "Исследование.")
    before = report.get_report_state()
    with pytest.raises(ValueError, match="верси"):
        report.append_or_update_section("# Вывод", "Вывод.", state["revision"])
    assert report.get_report_state() == before


def test_docx_export_is_readable_and_does_not_overwrite(report, tmp_path):
    report.create_report({"work_theme": "Проверка экспорта"})
    add_section(report, "# Цель работы", "Исследование.")
    result = export(report, "Отчёт.docx")
    target = tmp_path / "Отчёт.docx"
    data = target.read_bytes()
    assert result["path"] == str(target)
    assert result["size_bytes"] == len(data)
    assert "Исследование." in "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    with pytest.raises(ValueError, match="существует"):
        export(report, "Отчёт.docx")
    assert target.read_bytes() == data


@pytest.mark.parametrize("filename", [
    "../outside.docx", "sub/report.docx", "sub\\report.docx", "/report.docx",
    "C:\\report.docx", "CON.docx", "report.txt", "report.docx ", ".hidden.docx",
])
def test_export_rejects_unsafe_filenames(report, tmp_path, filename):
    report.create_report()
    with pytest.raises(ValueError):
        export(report, filename)
    assert list(tmp_path.iterdir()) == []


def test_export_cannot_follow_a_symlink(report, tmp_path):
    outside = tmp_path.parent / "outside.docx"
    outside.write_bytes(b"original")
    (tmp_path / "report.docx").symlink_to(outside)
    report.create_report()
    with pytest.raises(ValueError):
        export(report, "report.docx")
    assert outside.read_bytes() == b"original"


def test_export_checks_all_revisions_before_writing(report, tmp_path):
    state = report.create_report()
    report.update_meta({"work_theme": "Новая тема"}, state["meta_revision"])
    with pytest.raises(ValueError, match="верси"):
        report.export_report("report.docx", state["revision"], state["meta_revision"], state["image_revision"])
    assert list(tmp_path.iterdir()) == []


def test_image_upload_is_revision_checked_and_can_be_exported(report):
    state = report.create_report()
    sample_png = b"\x89PNG\r\n\x1a\n" + b"payload"
    revisions = report.upload_image(
        "screen.png", sample_png, state["image_revision"],
        caption="Снимок", insert_into_report=True,
        expected_revision=state["revision"],
    )
    image = report.list_images()[0]
    assert image["filename"] == "screen.png"
    assert image["is_in_report"] is True
    assert report.get_image("screen.png") == sample_png
    with pytest.raises(ValueError, match="ссылку"):
        report.delete_image("screen.png", revisions["image_revision"])


def test_image_upload_rejects_duplicate_and_stale_revision(report):
    state = report.create_report()
    sample_png = b"\x89PNG\r\n\x1a\n" + b"payload"
    report.upload_image("screen.png", sample_png, state["image_revision"])
    with pytest.raises(ValueError, match="уже прикреплено"):
        report.upload_image("screen.png", sample_png, report.get_report_state()["image_revision"])
    with pytest.raises(ValueError, match="верси"):
        report.upload_image("other.png", sample_png, state["image_revision"])


def test_autofix_and_lint_are_in_memory(report):
    report.create_report()
    add_section(report, "# Цель работы.", 'Текст "в кавычках".')
    state = report.get_report_state()
    fixed = report.autofix_typography(state["revision"])
    assert "# Цель работы" in report.get_report_state()["markdown_content"]
    assert "«в\u00a0кавычках»" in report.get_report_state()["markdown_content"]
    assert fixed["revision"] == report.get_report_state()["revision"]
    result = report.lint_report()
    assert "score" in result


def test_output_directory_must_already_exist(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(ValueError):
        HeadlessReport(missing)
    assert not missing.exists()


def test_pdf_export_requires_a_local_converter(report, monkeypatch):
    monkeypatch.setenv("REPORT_ENGINE_DISABLE_PDF", "1")
    report.create_report()
    report.lint_report()
    state = report.get_report_state()
    with pytest.raises(RuntimeError, match="PDF недоступен"):
        report.export_report(
            "report.pdf",
            state["revision"],
            state["meta_revision"],
            state["image_revision"],
            "pdf",
        )


def test_batch_returns_status_calls_in_order(report):
    report.create_report()
    result, payload = call_tool(report, "batch", {"calls": [
        {"name": "get_report_state", "arguments": {}},
        {"name": "list_images", "arguments": {}},
    ]})
    assert result.is_error is False
    assert [item["name"] for item in payload] == ["get_report_state", "list_images"]
    assert all(item["ok"] for item in payload)
    assert payload[0]["result"] == report.get_report_state()
    assert payload[1]["result"] == {"images": []}


def test_batch_creates_report_and_updates_metadata(report, tmp_path):
    expected = HeadlessReport(tmp_path).create_report()["meta_revision"]
    result, payload = call_tool(report, "batch", {"calls": [
        {"name": "create_report", "arguments": {}},
        {"name": "update_meta", "arguments": {
            "fields": {"work_theme": "Проверка"}, "expected_meta_revision": expected,
        }},
        {"name": "get_report_state", "arguments": {}},
    ]})
    assert result.is_error is False
    assert all(item["ok"] for item in payload)
    assert payload[2]["result"]["metadata"]["work_theme"] == "Проверка"


@pytest.mark.parametrize("stop_on_error, count", [(False, 3), (True, 2)])
def test_batch_collects_errors_and_optionally_stops(report, stop_on_error, count):
    result, payload = call_tool(report, "batch", {"stop_on_error": stop_on_error, "calls": [
        {"name": "create_report", "arguments": {}},
        {"name": "unknown", "arguments": {}},
        {"name": "get_report_state", "arguments": {}},
    ]})
    assert result.is_error is False
    assert len(payload) == count
    assert payload[0]["ok"] is True
    assert payload[1] == {"name": "unknown", "ok": False, "error": "Неизвестный инструмент: unknown"}
    if not stop_on_error:
        assert payload[2]["ok"] is True


@pytest.mark.parametrize("calls", [
    [], [{"name": "list_images", "arguments": {}}] * 21,
    [{"name": "create_report", "arguments": {}}, {"name": "batch", "arguments": {}}],
    [{"name": "create_report", "arguments": {}}, {"name": "list_images", "arguments": []}],
])
def test_invalid_batch_is_rejected_before_any_call(report, calls):
    result, _ = call_tool(report, "batch", {"calls": calls})
    assert result.is_error is True
    assert report.metadata is None


def test_batch_allows_export_and_preserves_image_content(report, tmp_path):
    state = report.create_report()
    sample = b"\x89PNG\r\n\x1a\n" + b"payload"
    report.upload_image("screen.png", sample, state["image_revision"])
    state = report.get_report_state()
    result, payload = call_tool(report, "batch", {"calls": [
        {"name": "get_image", "arguments": {"filename": "screen.png"}},
        {"name": "lint_report", "arguments": {}},
        {"name": "export_report", "arguments": {
            "filename": "report.docx", **{f"expected_{key}": state[key] for key in (
                "revision", "meta_revision", "image_revision",
            )},
        }},
    ]})
    assert result.is_error is False
    assert all(item["ok"] for item in payload)
    assert base64.b64decode(payload[0]["result"]["content"][0]["data"]) == sample
    assert "score" in payload[1]["result"]
    assert payload[2]["result"]["path"] == str(tmp_path / "report.docx")
    assert (tmp_path / "report.docx").is_file()


@pytest.mark.parametrize("path_kind", ["absolute", "relative", "home"])
def test_upload_image_reads_file_path(report, tmp_path, monkeypatch, path_kind):
    state = report.create_report()
    sample = b"\x89PNG\r\n\x1a\n" + b"payload"
    path = tmp_path / "source.png"
    path.write_bytes(sample)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    file_path = {"absolute": str(path), "relative": "source.png", "home": "~/source.png"}[path_kind]
    result, payload = call_tool(report, "upload_image", {
        "filename": "Снимок экрана.png", "file_path": file_path,
        "expected_image_revision": state["image_revision"], "expected_revision": state["revision"],
        "caption": "Снимок", "insert_into_report": True,
    })
    assert result.is_error is False
    assert report.get_image("Снимок_экрана.png") == sample
    assert "![Снимок](Снимок_экрана.png)" in report.content
    assert payload["image_revision"] != state["image_revision"]


@pytest.mark.parametrize("source, message", [
    ({}, "base64_data или file_path"),
    ({"file_path": "source.png", "base64_data": "AAAA"}, "base64_data или file_path"),
    ({"file_path": "missing.png"}, "не найден"),
    ({"file_path": ""}, "непустой строкой"),
])
def test_upload_image_rejects_invalid_file_source(report, tmp_path, source, message):
    state = report.create_report()
    if source.get("file_path"):
        source = {**source, "file_path": str(tmp_path / source["file_path"])}
    result, _ = call_tool(report, "upload_image", {
        "filename": "screen.png", "expected_image_revision": state["image_revision"], **source,
    })
    assert result.is_error is True
    assert message in result.content[0].text
    assert report.get_report_state() == state


def test_upload_images_reads_two_files_with_one_revision(report, tmp_path):
    state = report.create_report()
    sample = b"\x89PNG\r\n\x1a\n" + b"payload"
    images = []
    for name in ("one.png", "two.png"):
        path = tmp_path / name
        path.write_bytes(sample)
        images.append({"filename": name, "file_path": str(path), "caption": name, "insert_into_report": True})
    result, payload = call_tool(report, "upload_images", {
        "images": images, "expected_image_revision": state["image_revision"],
        "expected_revision": state["revision"],
    })
    assert result.is_error is False
    assert payload["uploaded_count"] == 2
    assert all(item["ok"] for item in payload["results"])
    assert [image["filename"] for image in report.list_images()] == ["one.png", "two.png"]
    assert report.content.index("one.png") < report.content.index("two.png")
    assert all(image["is_in_report"] for image in report.list_images())


def test_upload_images_collects_duplicate_and_oversized_file_errors(report, tmp_path):
    from backend.app.engine.headless_report import MAX_IMAGE_SIZE

    state = report.create_report()
    path = tmp_path / "large.png"
    with path.open("wb") as output:
        output.truncate(MAX_IMAGE_SIZE + 1)
    encoded = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"payload").decode()
    result, payload = call_tool(report, "upload_images", {
        "expected_image_revision": state["image_revision"], "images": [
            {"filename": "Схема сети.png", "base64_data": encoded},
            {"filename": "Схема_сети.png", "base64_data": encoded},
            {"filename": "large.png", "file_path": str(path)},
            {"filename": "last.png", "base64_data": encoded},
        ],
    })
    assert result.is_error is False
    assert payload["uploaded_count"] == 2
    assert [item["ok"] for item in payload["results"]] == [True, False, False, True]
    assert "уже прикреплено" in payload["results"][1]["error"]
    assert "15 МБ" in payload["results"][2]["error"]
    assert set(report.images) == {"Схема_сети.png", "last.png"}


def test_upload_image_reports_file_read_oserror_without_state_change(report, tmp_path, monkeypatch):
    from pathlib import Path

    state = report.create_report()
    path = tmp_path / "screen.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")

    def denied_open(self, *args, **kwargs):
        raise PermissionError("Access denied")

    monkeypatch.setattr(Path, "open", denied_open)
    result, _ = call_tool(report, "upload_image", {
        "filename": "screen.png", "file_path": str(path), "expected_image_revision": state["image_revision"],
    })
    assert result.is_error is True
    assert result.content[0].text == "Не удалось прочитать файл изображения"
    assert report.get_report_state() == state


@pytest.mark.parametrize("extra_byte", [False, True])
def test_upload_image_file_size_boundary(report, tmp_path, extra_byte):
    from backend.app.engine.headless_report import MAX_IMAGE_SIZE

    state = report.create_report()
    path = tmp_path / "screen.png"
    with path.open("wb") as output:
        output.write(b"\x89PNG\r\n\x1a\n")
        output.truncate(MAX_IMAGE_SIZE + int(extra_byte))
    result, _ = call_tool(report, "upload_image", {
        "filename": "screen.png", "file_path": str(path), "expected_image_revision": state["image_revision"],
    })
    assert result.is_error is extra_byte
    if extra_byte:
        assert "15 МБ" in result.content[0].text
        assert report.get_report_state() == state
    else:
        assert len(report.get_image("screen.png")) == MAX_IMAGE_SIZE


@pytest.mark.parametrize("images", [None, [], [{}] * 151])
def test_upload_images_rejects_invalid_array_without_state_change(report, images):
    state = report.create_report()
    result, _ = call_tool(report, "upload_images", {
        "images": images, "expected_image_revision": state["image_revision"],
    })
    assert result.is_error is True
    assert "от 1 до 150" in result.content[0].text
    assert report.get_report_state() == state


def test_upload_images_continues_after_bad_source_and_signature(report):
    state = report.create_report()
    encoded = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
    result, payload = call_tool(report, "upload_images", {
        "expected_image_revision": state["image_revision"], "images": [
            {"filename": "both.png", "base64_data": encoded, "file_path": "unused.png"},
            {"filename": "bad.png", "base64_data": "!!!"},
            {"filename": "screen.bmp", "base64_data": base64.b64encode(b"BMpayload").decode()},
            {"filename": "valid.png", "base64_data": encoded},
        ],
    })
    assert result.is_error is False
    assert [item["ok"] for item in payload["results"]] == [False, False, False, True]
    assert payload["uploaded_count"] == 1
    assert list(report.images) == ["valid.png"]


def test_core_upload_images_checks_revisions_before_any_write(report):
    state = report.create_report()
    images = [{"filename": "one.png", "data": b"\x89PNG\r\n\x1a\n", "insert_into_report": True}]
    with pytest.raises(ValueError, match="верси"):
        report.upload_images(images, "stale", expected_revision=state["revision"])
    with pytest.raises(ValueError, match="revision текста"):
        report.upload_images(images, state["image_revision"])
    assert report.get_report_state() == state


def test_bmp_remains_unsupported(report):
    state = report.create_report()
    with pytest.raises(ValueError, match="поддерживаемое изображение"):
        report.upload_image("screen.bmp", b"BMpayload", state["image_revision"])
    assert report.get_report_state() == state


def test_headless_manifest_registers_batch_and_both_image_sources():
    from backend.app.headless import _tools
    from backend.app.engine.headless_report import MAX_IMAGES_COUNT

    schemas = {tool.name: tool.input_schema for tool in _tools()}
    assert schemas["batch"]["properties"]["calls"]["maxItems"] == 20
    assert schemas["upload_images"]["properties"]["images"]["maxItems"] == MAX_IMAGES_COUNT
    for name in ("upload_image", "upload_images"):
        assert "expected_image_revision" in schemas[name]["required"]
    assert "file_path" in schemas["upload_image"]["properties"]
    assert "base64_data" not in schemas["upload_image"]["required"]
    assert "file_path" in schemas["upload_images"]["properties"]["images"]["items"]["properties"]
