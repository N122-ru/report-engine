import io
import os
import sys

sys.path.insert(0, os.path.abspath("backend"))

from fastapi.testclient import TestClient

from app.engine.docx_import import parse_docx_bytes
from app.engine.generator import build_docx_report
from app.engine.sessions import session_manager
from app.main import app
from app.models.report import GenerateOptions, ReportMetadata


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0dIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99\x3d\x1d"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _generated_docx(markdown: str, metadata: ReportMetadata, images=None) -> bytes:
    return build_docx_report(
        metadata,
        markdown,
        images_dict=images or {},
        options=GenerateOptions(latex_mode="omml"),
    ).getvalue()


def test_import_generated_docx_preserves_editable_body_features():
    markdown = (
        "# Цель работы\nЦель импортирования.\n\n"
        "# Ход работы\n– Первый шаг\n– Второй шаг\n\n"
        "Таблица 1 — Параметры\n"
        "| Параметр | Значение |\n| --- | --- |\n| Режим | Тест |\n\n"
        "![Схема стенда](diagram.png)\n\n"
        "$$x^2 + y^2$$"
    )
    result = parse_docx_bytes(
        _generated_docx(
            markdown,
            ReportMetadata(work_theme="Тестовая схема", discipline="Инженерная дисциплина"),
            {"diagram.png": PNG_1X1},
        )
    )

    assert "# Цель работы" in result["markdown"]
    assert "- Первый шаг" in result["markdown"]
    assert "- Второй шаг" in result["markdown"]
    assert "Таблица 1 — Параметры" in result["markdown"]
    assert "| Параметр | Значение |" in result["markdown"]
    imported_name = result["uploaded_images"][0]["filename"]
    assert f"![Схема стенда]({imported_name})" in result["markdown"]
    assert imported_name == "image1.png"
    assert "Рисунок 1 — Схема стенда" not in result["markdown"]
    assert "Формула" in " ".join(result["warnings"])


def test_import_title_hints_recognize_samgtu_style_title_page():
    metadata = ReportMetadata(
        university="САМГТУ",
        institute="Институт вымышленных систем",
        department="Кафедра испытаний",
        work_type="о выполнении лабораторной работы",
        work_number=7,
        work_theme="Проверка импортирования",
        discipline="Основы отчётности",
        teachers=[{"fio": "И.И. Вымышленный", "role": "доцент"}],
        students=[
            {"fio": "П.П. Примеров", "group": "ИВТ-101"},
            {"fio": "А.А. Образцов", "group": "ИВТ-101"},
        ],
        city="Тестоград",
        year=2025,
    )
    result = parse_docx_bytes(_generated_docx("# Цель работы\nТекст.", metadata))

    hints = result["meta_hints"]
    assert hints["work_type"] == "о выполнении лабораторной работы"
    assert hints["work_number"] == 7
    assert hints["work_theme"] == "Проверка импортирования"
    assert hints["discipline"] == "Основы отчётности"
    assert hints["teachers"] == [{"fio": "И.И. Вымышленный", "role": "доцент"}]
    assert hints["students"] == [
        {"fio": "П.П. Примеров", "group": "ИВТ-101"},
        {"fio": "А.А. Образцов", "group": "ИВТ-101"},
    ]
    assert hints["city"] == "Тестоград"
    assert hints["year"] == 2025


def test_docx_import_endpoint_requires_session_and_rejects_non_docx():
    client = TestClient(app)
    document = _generated_docx("# Раздел\nТекст.", ReportMetadata())

    unauthorized = client.post(
        "/api/import/docx",
        files={"file": ("report.docx", document, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert unauthorized.status_code == 401

    session = session_manager.get_or_create()
    invalid = client.post(
        f"/api/import/docx?token={session.token}",
        files={"file": ("report.txt", b"not a docx", "text/plain")},
    )
    assert invalid.status_code == 400
    corrupt = client.post(
        f"/api/import/docx?token={session.token}",
        files={"file": ("report.docx", b"not a docx", "application/octet-stream")},
    )
    assert corrupt.status_code == 400

    imported = client.post(
        f"/api/import/docx?token={session.token}",
        files={"file": ("report.docx", document, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert imported.status_code == 200
    assert imported.json()["markdown"].startswith("# Раздел")
