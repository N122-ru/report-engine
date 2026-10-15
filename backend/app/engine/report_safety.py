"""Share stateless report guards and in-memory verification across MCP transports."""

import hashlib
import json
from collections import OrderedDict
from copy import deepcopy
from typing import Any
import re

from markdown_it import MarkdownIt

from .markdown_parser import _find_image_bytes
from .section_editor import sections

MAX_MARKDOWN_BYTES = 500 * 1024
OPERATION_CACHE_MAX_BYTES = 8 * 1024 * 1024
OPERATION_RESULT_MAX_BYTES = 256 * 1024
MAX_OPERATION_ID_LENGTH = 128
BLOCKING_KINDS = frozenset({"placeholder", "missing_image"})
REVISION_FIELDS = ("revision", "meta_revision", "image_revision")
LARGE_FINGERPRINT_FIELDS = frozenset({"base64_data", "data"})
GUARDS = (
    ("placeholder", re.compile(
        r"\b(?:данных|информации|сведений|результатов)\s+(?:нет|недостаточно)\b|"
        r"\b(?:информация|данные|сведения|результаты)\s+(?:отсутству\w*|не\s+(?:предоставлен\w*|указан\w*))\b|"
        r"\b(?:нет|отсутству\w*)\s+(?:данных|информации|сведений)\b|"
        r"\bна\s+скриншоте\b[^.!?\n]{0,100}\b(?:нет|не\s+(?:видно|указан\w*)|отсутству\w*)\b|"
        r"\b(?:требуется|нужно)\s+уточнить\s+(?:данные|информацию|результаты)\b", re.I),
     "В тексте обнаружена заглушка о недостающих данных. Задайте вопрос пользователю вне отчёта."),
    ("internal_path", re.compile(
        r"(?<![\w:/])/(?:home|Users|data)/[^\s]+|\b[A-Za-z]:[\\/]Users[\\/][^\s]+", re.I),
     "В прозе обнаружен внутренний путь. Уберите сведения о подготовке документа."),
    ("preparation_note", re.compile(
        r"\b(?:на|из)\s+(?:(?:данном|предоставленном|прикрепл[её]нном|этом)\s+)?скриншот[ае]\b|"
        r"\b(?:прикрепл[её]н\w*|приложен\w*|загружен\w*)\s+(?:файл\w*|скриншот\w*)\b|"
        r"\b(?:в|из)\s+(?:прикрепл[её]нн\w*|приложенн\w*|загруженн\w*)\s+файл\w*\b|"
        r"\bкак\s+указано\s+в\s+задании\s+в\s+файле\b", re.I),
     "Обнаружено служебное описание скриншота или файла. Опишите результат работы и ссылку на рисунок."),
)


def image_references(markdown: str, images: dict[str, bytes]) -> list[dict[str, Any]]:
    """Resolve real Markdown images using the generator's attachment matching."""
    result = []
    for token in MarkdownIt("commonmark").parse(markdown):
        for child in token.children or []:
            if child.type != "image":
                continue
            src = child.attrGet("src") or ""
            external = src.lower().startswith(("http://", "https://", "data:", "blob:"))
            result.append({
                "filename": src,
                "status": "attached" if external or _find_image_bytes(src, images) is not None else "missing",
                "location": f"Строка {(token.map or [0])[0] + 1}",
            })
    return result


def lint_content_guards(markdown: str, images: dict[str, bytes]) -> dict[str, list]:
    """Detect unresolved prose without inspecting code, link targets, or image captions."""
    items = []

    def add(kind: str, message: str, location: str) -> None:
        identity = hashlib.sha256(f"{kind}:{location}:{message}".encode()).hexdigest()[:20]
        items.append({"id": f"{kind}:{identity}", "kind": kind, "message": message, "location": location})

    for token in MarkdownIt("commonmark").parse(markdown):
        if token.type != "inline":
            continue
        # Separate literal spans so two prose fragments cannot form a false phrase.
        prose = "".join(child.content if child.type == "text" else " " for child in token.children or [])
        for kind, pattern, message in GUARDS:
            if pattern.search(prose):
                add(kind, message, f"Строка {(token.map or [0])[0] + 1}: {prose.strip()[:120]}")
    seen = set()
    for ref in image_references(markdown, images):
        if ref["status"] == "missing" and ref["filename"] not in seen:
            seen.add(ref["filename"])
            add("missing_image", f"Изображение «{ref['filename']}» не прикреплено.", ref["location"])
    return {"unresolved_items": items, "export_blockers": [item for item in items if item["kind"] in BLOCKING_KINDS]}


def add_content_guards(result: dict[str, Any], markdown: str, images: dict[str, bytes]) -> dict[str, Any]:
    """Extend an existing lint result without changing legacy validity semantics."""
    guards = lint_content_guards(markdown, images)
    # Missing-image warnings already come from DOCX placeholders.
    warnings = [{"type": item["kind"].upper(), "severity": "WARNING", "message": item["message"],
                 "location": item["location"], "fix_suggestion": "Уточните исходные данные у пользователя"}
                for item in guards["unresolved_items"] if item["kind"] != "missing_image"]
    result["warnings"] = result["warnings"] + warnings
    result["score"] = max(0, result["score"] - 4 * len(warnings))
    if warnings and result.get("status") == "ready":
        result["status"] = "needs_review"
    return result | guards


def report_digest(markdown: str, images: dict[str, bytes]) -> dict[str, Any]:
    """Return section headings and word counts without disclosing the full body."""
    return {
        "sections": [{"heading": section.heading, "word_count": len(markdown[section.body_start:section.end].split())}
                     for section in sections(markdown)],
        "image_refs": image_references(markdown, images),
    }


def validate_detail(detail: Any) -> None:
    """Reject unknown state modes rather than silently returning the full body."""
    if detail not in ("full", "digest"):
        raise ValueError("detail должен быть full или digest")


def snapshot_id(revisions: dict[str, str]) -> str:
    """Return one digest for the text, metadata, and image revisions."""
    try:
        values = [revisions[field] for field in REVISION_FIELDS]
    except KeyError as exc:
        raise ValueError("Неполный набор ревизий отчёта") from exc
    payload = "\0".join(values).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def with_snapshot(revisions: dict[str, str]) -> dict[str, str]:
    """Add the combined snapshot identifier without changing legacy fields."""
    current = {field: revisions[field] for field in REVISION_FIELDS}
    return current | {"snapshot_id": snapshot_id(current)}


def conflict_payload(message: str, revisions: dict[str, str]) -> dict[str, Any]:
    """Build the stable machine-readable detail for a revision conflict."""
    return {
        "error": message,
        "conflict": True,
        "current": with_snapshot(revisions),
        "next_action": "refresh_and_retry",
    }


def is_conflict_message(message: str) -> bool:
    """Recognize revision errors from both legacy and unified wording."""
    return any(marker in message.lower() for marker in (
        "конфликт версий", "документ изменился", "реквизиты изменились",
        "набор изображений изменился", "отчёт изменился",
    ))


def require_revision_guard(
    arguments: dict[str, Any], fields: tuple[str, ...], *, alternatives: tuple[str, ...] = (),
) -> None:
    """Require an atomic snapshot or the legacy revision arguments for a mutation."""
    if arguments.get("expected_snapshot_id") is not None:
        return
    required = alternatives or tuple(
        field if field.startswith("expected_") else f"expected_{field}" for field in fields
    )
    if alternatives:
        present = any(arguments.get(field) is not None for field in alternatives)
        missing = [] if present else list(alternatives)
    else:
        missing = [field for field in required if arguments.get(field) is None]
    if missing:
        names = " или ".join(missing) if alternatives else ", ".join(missing)
        raise ValueError(
            f"Передайте expected_snapshot_id или актуальные параметры версий: {names}"
        )


def operation_fingerprint(arguments: dict[str, Any], operation_name: str = "") -> str:
    """Hash operation arguments without serializing large binary payloads twice."""

    def compact(value: Any, key: str | None = None) -> Any:
        if isinstance(value, bytes):
            return {"__sha256__": hashlib.sha256(value).hexdigest(), "__length__": len(value)}
        if isinstance(value, str) and key in LARGE_FINGERPRINT_FIELDS:
            return {
                "__sha256__": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                "__length__": len(value),
            }
        if isinstance(value, dict):
            return {name: compact(item, name) for name, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [compact(item) for item in value]
        return value

    payload = compact({key: value for key, value in arguments.items() if key != "operation_id"})
    if operation_name:
        payload["__operation_name__"] = operation_name
    try:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), default=repr)
    except (TypeError, ValueError):
        encoded = repr(payload)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class OperationCache:
    """Keep bounded successful idempotent operation results using byte-based LRU."""

    def __init__(self, limit: int = 100, max_bytes: int = OPERATION_CACHE_MAX_BYTES) -> None:
        self.limit = limit
        self.max_bytes = max_bytes
        self._bytes = 0
        self._entries: OrderedDict[str, tuple[str, Any, int]] = OrderedDict()

    @staticmethod
    def _size(value: Any) -> int:
        """Estimate the UTF-8 payload size used by the cached MCP result."""
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json", by_alias=True, exclude_none=True)
        try:
            return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=repr).encode("utf-8"))
        except (TypeError, ValueError):
            return len(repr(value).encode("utf-8"))

    @staticmethod
    def _validate_id(operation_id: Any) -> str:
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError("Параметр «operation_id» должен быть непустой строкой")
        if len(operation_id) > MAX_OPERATION_ID_LENGTH:
            raise ValueError(f"Параметр «operation_id» не может быть длиннее {MAX_OPERATION_ID_LENGTH} символов")
        return operation_id

    def lookup(self, operation_id: Any, arguments: dict[str, Any], operation_name: str = "",
               *, fingerprint: str | None = None) -> Any:
        """Return a cached result, reusing a precomputed fingerprint when supplied."""
        if operation_id is None:
            return None
        operation_id = self._validate_id(operation_id)
        if fingerprint is None:
            fingerprint = operation_fingerprint(arguments, operation_name)
        entry = self._entries.get(operation_id)
        if entry is None:
            return None
        saved_fingerprint, result, _ = entry
        if saved_fingerprint != fingerprint:
            raise ValueError("operation_id уже использован с другими аргументами")
        self._entries.move_to_end(operation_id)
        return deepcopy(result)

    def store(self, operation_id: Any, arguments: dict[str, Any], result: Any,
              operation_name: str = "", *, fingerprint: str | None = None) -> dict[str, Any] | None:
        """Store one successful operation, reusing a precomputed fingerprint when supplied."""
        if operation_id is None:
            return
        operation_id = self._validate_id(operation_id)
        result_size = self._size(result)
        if result_size > OPERATION_RESULT_MAX_BYTES:
            self._remove(operation_id)
            return {"cached": False, "reason": "result_too_large"}
        self._remove(operation_id)
        self._entries[operation_id] = (
            fingerprint if fingerprint is not None else operation_fingerprint(arguments, operation_name),
            deepcopy(result), result_size,
        )
        self._bytes += result_size
        self._entries.move_to_end(operation_id)
        while len(self._entries) > self.limit or self._bytes > self.max_bytes:
            _, (_, _, size) = self._entries.popitem(last=False)
            self._bytes -= size

    def _remove(self, operation_id: str) -> None:
        """Remove one cache entry and maintain the byte accounting."""
        entry = self._entries.pop(operation_id, None)
        if entry is not None:
            self._bytes -= entry[2]

    def clear(self) -> None:
        """Discard cached results after a resource deletion."""
        self._entries.clear()
        self._bytes = 0


class ReportVerification:
    """Require a successful lint after every actual mutation, including rollbacks."""

    def __init__(self) -> None:
        self.change_sequence = 0
        self.lint_sequence: int | None = None
        self.lint_revisions: dict[str, str] | None = None
        self.lint_result: dict[str, Any] | None = None

    def changed(self) -> None:
        """Invalidate earlier lint even if a later edit restores identical hashes."""
        self.change_sequence += 1

    def record_lint(self, revisions: dict[str, str], result: dict[str, Any]) -> None:
        """Record only a completed lint of the current report, not a review snapshot."""
        self.lint_sequence = self.change_sequence
        self.lint_revisions = dict(revisions)
        self.lint_result = deepcopy(result)

    def state(self, revisions: dict[str, str]) -> dict[str, bool]:
        """Expose strict export readiness independently of legacy DOCX validity."""
        current = self.lint_sequence == self.change_sequence and self.lint_revisions == revisions
        return {"lint_after_last_change": current,
                "export_allowed": current and not bool((self.lint_result or {}).get("export_blockers"))}

    def require_export(self, revisions: dict[str, str], confirm: Any = False) -> None:
        """Allow literal true to bypass blockers, never the mandatory lint phase."""
        if type(confirm) is not bool:
            raise ValueError("confirm_blocked_export должен быть логическим значением")
        if not self.state(revisions)["lint_after_last_change"]:
            raise ValueError(
                "Сначала проверь отчёт через lint_report после последнего изменения "
                "(выполните lint_report после последнего изменения отчёта)"
            )
        blockers = (self.lint_result or {}).get("export_blockers", [])
        if blockers and confirm is not True:
            import json
            raise ValueError("Экспорт заблокирован: " + json.dumps(blockers, ensure_ascii=False)
                             + ". Для явного подтверждения передайте confirm_blocked_export: true")
