"""Locate the canonical core and allowlisted references in source and frozen runtimes."""

import hashlib
import os
import sys
from pathlib import Path

from .image_input import MAX_IMAGE_SIZE, MAX_IMAGES_COUNT
from .pdf_converter import pdf_export_status
from .report_safety import MAX_MARKDOWN_BYTES

REFERENCE_NAMES = ("figures", "formulas", "tables", "style", "literals")
CONTRACT_VERSION = "1.3"
LIVE_TOOL_NAMES = frozenset({
    "batch", "list_images", "get_image", "get_images", "upload_image", "upload_images",
    "update_image_layout", "get_report_state", "append_or_update_section", "patch_text",
    "apply_patches", "get_document_outline", "replace_block", "delete_block", "move_figure",
    "get_last_edit", "get_edit_history", "rollback_last_edit", "lint_report",
    "autofix_typography", "update_meta", "delete_image", "delete_images", "import_profile",
    "get_capabilities", "review_snapshot", "export_report",
})
HEADLESS_TOOL_NAMES = frozenset({
    "batch", "create_report", "import_profile", "get_report_state", "get_capabilities",
    "review_snapshot", "list_images", "get_image", "get_images", "upload_image", "upload_images",
    "append_or_update_section", "update_meta", "delete_image", "lint_report",
    "autofix_typography", "export_report",
})


def read_agent_asset(relative: str) -> str:
    """Read one trusted asset path, preferring the frozen runtime when present."""
    roots = []
    runtime = getattr(sys, "_MEIPASS", None)
    if runtime:
        roots.append(Path(runtime) / "assets")
    roots.extend((Path(__file__).resolve().parents[3] / "assets",
                  Path(__file__).resolve().parents[2] / "assets", Path.cwd() / "assets"))
    for root in roots:
        path = root / relative
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    raise ValueError("Файл инструкции агента недоступен")


def reference_resources() -> list[dict[str, str]]:
    """Advertise the fixed set of domain references shared by both transports."""
    return [{"uri": f"report://reference/{name}", "name": f"Справочник: {name}",
             "mimeType": "text/markdown"} for name in REFERENCE_NAMES]


def read_reference(uri: str) -> str:
    """Reject arbitrary paths instead of interpreting a resource URI as a filename."""
    name = uri.removeprefix("report://reference/")
    if uri != f"report://reference/{name}" or name not in REFERENCE_NAMES:
        raise ValueError("Справочник не найден")
    return read_agent_asset(f"reference/{name}.md")


def resource_versions() -> list[dict[str, str | int]]:
    """Return hashes and byte sizes for every cacheable agent resource."""
    resources = [("report://rules/gost732", "SKILL.md")]
    resources.extend(
        (f"report://reference/{name}", f"reference/{name}.md")
        for name in REFERENCE_NAMES
    )
    result = []
    for uri, relative in resources:
        content = read_agent_asset(relative).encode("utf-8")
        result.append({
            "uri": uri,
            "sha256": hashlib.sha256(content).hexdigest()[:12],
            "bytes": len(content),
        })
    return result


def agent_onboarding_prompt(
    client_agent: str, notes: str = "", *, include_file_path: bool = False,
) -> str:
    """Build a client-local onboarding dialogue without storing user answers."""
    if not isinstance(client_agent, str) or not client_agent.strip():
        raise ValueError("Параметр «client_agent» должен быть непустой строкой")
    if not isinstance(notes, str):
        raise ValueError("Параметр «notes» должен быть строкой")
    note_block = (
        f"\nПереданные пользователем заметки о клиенте (не выдумывай ответы): {notes.strip()}\n"
        if notes.strip() else ""
    )
    file_path_shortcut = (
        "- Используй file_path только если агент работает на одной машине с сервером или в standalone; "
        "в web-режиме этот вариант не используй.\n"
        if include_file_path else ""
    )
    return (
        f"Клиентский агент «{client_agent.strip()}» сам задаёт пользователю вопросы в своём чате; "
        "серверного ask_user нет и ответы пользователя нельзя выдумывать или записывать на сервер.\n"
        "Сначала задай пользователю 4 вопроса:\n"
        "1. Кто вы и для какой работы нужен Report Engine?\n"
        "2. Где лежат исходники и фотографии, которые можно использовать?\n"
        "3. Нужна ли финальная независимая проверка субагентом?\n"
        "4. Нужен одноразовый (one-shot) сценарий или интерактивный режим?\n"
        "После ответов подставь их в следующую локальную памятку. Не добавляй в неё "
        "неподтверждённые сведения; сервер её не хранит.\n"
        f"{note_block}\n"
        "## Локальная памятка агента\n"
        "### Назначение MCP у этого пользователя\n"
        "[Кратко опиши назначение MCP на основе ответов пользователя.]\n\n"
        "### Клиентские шорткаты\n"
        "- Используй batch вместо серий одинаковых вызовов.\n"
        "- Используй digest вместо полного state, когда полный текст не нужен.\n"
        f"{file_path_shortcut}"
        "- Передавай operation_id на мутациях от слабых клиентов.\n\n"
        "### Правило приоритета источников\n"
        "report://rules/gost732 ядро > report://reference/* > локальные шорткаты; "
        "локальный скилл не переопределяет серверные правила.\n"
        "локальный скилл — кэш: сверяй версии с get_capabilities"
    )


def get_capabilities(transport: str) -> dict:
    """Describe the application contract separately from MCP protocol capabilities."""
    own = LIVE_TOOL_NAMES if transport == "live" else HEADLESS_TOOL_NAMES
    other = HEADLESS_TOOL_NAMES if transport == "live" else LIVE_TOOL_NAMES
    tools_diff = [
        {"name": name, "available_in": transport}
        for name in sorted(own - other)
    ] + [
        {"name": name, "available_in": "live" if transport == "headless" else "headless"}
        for name in sorted(other - own)
    ]
    file_path: object = "standalone" if transport == "headless" else False
    if transport == "live":
        root = live_file_root()
        if root is not None:
            file_path = {"root": str(root)}
    return {
        "transport": transport, "contract_version": CONTRACT_VERSION,
        **pdf_export_status(), "file_path": file_path,
        "limits": {"image_bytes": MAX_IMAGE_SIZE, "images_count": MAX_IMAGES_COUNT,
                   "markdown_bytes": MAX_MARKDOWN_BYTES},
        "reference_resources": [resource["uri"] for resource in reference_resources()],
        "resources": resource_versions(),
        "tools_diff": tools_diff,
    }


def live_file_root() -> Path | None:
    """Return the valid live-MCP file root configured by the environment."""
    raw = os.environ.get("REPORT_ENGINE_MCP_FILE_ROOT")
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        return None
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return None
    return resolved if resolved.is_dir() else None
