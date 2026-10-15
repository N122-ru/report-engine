"""Validation and loading for the portable report-engine profile format."""

import json
from typing import Any

from ..models.report import ReportMetadata
from .image_input import resolve_file_path


PROFILE_FORMAT = "report-engine-profile"
PROFILE_VERSION = 1
PROFILE_MAX_BYTES = 4 * 1024 * 1024
PROFILE_META_FIELDS = (
    "university", "ministry", "logo_mode", "custom_logo", "city", "institute",
    "department", "doc_type", "work_type", "work_number", "discipline",
    "students", "teachers", "year",
)
PROFILE_SUBJECT_FIELDS = {
    "id", "name", "institute", "department", "teachers", "custom_instructions", "last_work_number",
}


def _broken(message: str) -> ValueError:
    return ValueError(f"Профиль повреждён: {message}")


def _people(value: Any, kind: str) -> bool:
    if not isinstance(value, list) or not value:
        return False
    required = "group" if kind == "students" else "role"
    return all(
        isinstance(item, dict)
        and isinstance(item.get("fio"), str)
        and isinstance(item.get(required), str)
        for item in value
    )


def validate_profile(value: Any) -> dict[str, Any]:
    """Validate one profile at an external-input boundary."""
    try:
        if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > PROFILE_MAX_BYTES:
            raise _broken("размер профиля превышает 4 МБ")
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("Профиль повреждён:"):
            raise
        raise _broken("структура не может быть прочитана как JSON") from exc
    if not isinstance(value, dict) or set(value) - {"format", "version", "subject", "meta"} or value.get("format") != PROFILE_FORMAT:
        raise ValueError("Неверный формат файла профиля. Ожидается report-engine-profile.")
    if value.get("version") != PROFILE_VERSION:
        raise ValueError(
            f"Неподдерживаемая версия профиля: {value.get('version')}. "
            f"Ожидается версия {PROFILE_VERSION}."
        )

    subject = value.get("subject")
    meta = value.get("meta")
    if not isinstance(subject, dict) or not PROFILE_SUBJECT_FIELDS.issuperset(subject):
        raise _broken("некорректный шаблон дисциплины")
    if not all(isinstance(subject.get(field), str) for field in ("id", "name", "institute", "department")):
        raise _broken("некорректный шаблон дисциплины")
    if not _people(subject.get("teachers"), "teachers"):
        raise _broken("некорректный список преподавателей в шаблоне")
    if "custom_instructions" in subject and not isinstance(subject["custom_instructions"], str):
        raise _broken("некорректные указания преподавателя")
    if "last_work_number" in subject and (
        subject["last_work_number"] is not None
        and (type(subject["last_work_number"]) is not int or subject["last_work_number"] <= 0)
    ):
        raise _broken("некорректный последний номер работы")

    if not isinstance(meta, dict) or set(meta) - set(PROFILE_META_FIELDS):
        raise _broken("некорректные реквизиты титульного листа")
    required_strings = (
        "university", "ministry", "city", "institute", "department", "doc_type", "work_type", "discipline",
    )
    if not all(isinstance(meta.get(field), str) for field in required_strings):
        raise _broken("некорректные реквизиты титульного листа")
    if type(meta.get("work_number")) is not int or meta["work_number"] < 0:
        raise _broken("некорректный номер работы")
    if type(meta.get("year")) is not int:
        raise _broken("некорректный год")
    if not _people(meta.get("students"), "students") or not _people(meta.get("teachers"), "teachers"):
        raise _broken("некорректный состав студентов или преподавателей")
    if meta.get("logo_mode") not in {"default", "custom", "none"}:
        raise _broken("некорректный режим логотипа")
    if "custom_logo" in meta and meta["custom_logo"] is not None and not isinstance(meta["custom_logo"], str):
        raise _broken("некорректный пользовательский логотип")
    if meta.get("logo_mode") == "custom" and not isinstance(meta.get("custom_logo"), str):
        raise _broken("для режима custom нужен пользовательский логотип")
    if any(field not in meta for field in PROFILE_META_FIELDS if field != "custom_logo"):
        raise _broken("не хватает обязательных реквизитов титульного листа")

    try:
        ReportMetadata.model_validate(meta, strict=True)
    except ValueError as exc:
        raise _broken("реквизиты титульного листа не соответствуют схеме") from exc

    return {
        "format": PROFILE_FORMAT,
        "version": PROFILE_VERSION,
        "subject": dict(subject),
        "meta": dict(meta),
    }


def load_profile_input(args: dict[str, Any]) -> dict[str, Any]:
    """Read an inline profile or a local JSON file without accepting both."""
    profile = args.get("profile")
    file_path = args.get("file_path")
    if (profile is None) == (file_path is None):
        raise ValueError("Передайте profile или file_path, но не оба параметра")
    if profile is not None:
        return validate_profile(profile)
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("Параметр file_path должен быть непустой строкой")
    path = resolve_file_path(file_path)
    try:
        if not path.is_file() or path.stat().st_size > PROFILE_MAX_BYTES:
            raise ValueError("Файл профиля не найден или превышает допустимый размер")
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _broken("не удалось прочитать JSON-файл") from exc
    return validate_profile(parsed)


def profile_metadata(profile: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge profile values into report metadata while preserving report-only fields."""
    validated = validate_profile(profile)
    subject = validated["subject"]
    merged = {**(base or {}), **validated["meta"]}
    merged.update({
        "discipline": subject["name"],
        "institute": subject["institute"],
        "department": subject["department"],
        "teachers": subject["teachers"],
        "custom_instructions": subject.get("custom_instructions", ""),
    })
    return ReportMetadata.model_validate(merged).model_dump()
