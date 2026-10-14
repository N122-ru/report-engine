"""Share stateless report guards and in-memory verification across MCP transports."""

import hashlib
from copy import deepcopy
from typing import Any
import re

from markdown_it import MarkdownIt

from .markdown_parser import _find_image_bytes
from .section_editor import sections

MAX_MARKDOWN_BYTES = 500 * 1024
BLOCKING_KINDS = frozenset({"placeholder", "missing_image"})
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
            raise ValueError("Сначала проверь отчёт через lint_report после последнего изменения")
        blockers = (self.lint_result or {}).get("export_blockers", [])
        if blockers and confirm is not True:
            import json
            raise ValueError("Экспорт заблокирован: " + json.dumps(blockers, ensure_ascii=False)
                             + ". Для явного подтверждения передайте confirm_blocked_export: true")
