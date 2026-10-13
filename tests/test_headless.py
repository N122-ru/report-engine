import io
import subprocess
import sys

import pytest
from docx import Document

from backend.app.engine.headless_report import HeadlessReport


@pytest.fixture
def report(tmp_path):
    return HeadlessReport(tmp_path)


def add_section(report, heading, content):
    return report.append_or_update_section(
        heading, content, report.get_report_state()["revision"]
    )


def export(report, filename):
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
    state = report.get_report_state()
    with pytest.raises(RuntimeError, match="PDF недоступен"):
        report.export_report(
            "report.pdf",
            state["revision"],
            state["meta_revision"],
            state["image_revision"],
            "pdf",
        )
