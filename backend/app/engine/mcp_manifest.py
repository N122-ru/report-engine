"""Build isolated live MCP tool manifests for each transport environment."""

import copy
from typing import Any, Dict, List

from .local_files import local_files_enabled


MCP_TOOL_PAGE_SIZE = 10
MCP_TOOL_CURSOR_PREFIX = "report-live-tools-v1:"

# Keep the complete legacy workflow on the first page. Older clients that do
# not follow nextCursor still retain enough tools to create and validate a report.
MCP_CORE_TOOL_NAMES = (
    "list_images",
    "get_image",
    "get_images",
    "upload_image",
    "get_report_state",
    "append_or_update_section",
    "lint_report",
    "autofix_typography",
    "update_meta",
    "delete_image",
)

MCP_MUTATING_TOOLS = frozenset({
    "upload_image",
    "upload_images",
    "update_image_layout",
    "append_or_update_section",
    "patch_text",
    "apply_patches",
    "replace_block",
    "delete_block",
    "move_figure",
    "rollback_last_edit",
    "autofix_typography",
    "update_meta",
    "import_profile",
    "delete_image",
    "delete_images",
    "export_report",
})
MCP_OPERATION_TOOLS = MCP_MUTATING_TOOLS | {"get_images"}

_LOCAL_FILE_TOOL_NAMES = {"upload_image", "upload_images", "import_profile"}

_NETWORKED_TOOL_DESCRIPTIONS = {
    "upload_image": (
        "Загружает изображение (график matplotlib, схему) в сессию отчета. "
        "Изображение отображается в браузере в панели медиа и на страницах макета А4. "
        "Принимает имя файла и данные base64. Опционально может сразу вставить ссылку в Markdown."
    ),
    "upload_images": (
        "Атомарно загружает несколько рисунков из base64_data и при необходимости вставляет "
        "их после блоков из текущего outline."
    ),
    "import_profile": (
        "Импортирует профиль дисциплины и титульного листа формата report-engine-profile версии 1. "
        "Принимает JSON-объект profile. Требует свежую meta_revision."
    ),
}


def with_unified_mutation_fields(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return a detached manifest with additive snapshot and idempotency fields."""
    fields = {
        "expected_snapshot_id": {
            "type": "string",
            "description": "Атомарная snapshot_id из get_report_state; заменяет отдельные expected_*",
        },
        "operation_id": {
            "type": "string",
            "maxLength": 128,
            "description": "Необязательный ключ идемпотентности для безопасного повтора операции",
        },
    }
    result = copy.deepcopy(tools)
    for tool in result:
        if tool["name"] not in MCP_MUTATING_TOOLS and tool["name"] not in {"batch", "get_images"}:
            continue
        properties = tool["inputSchema"].setdefault("properties", {})
        properties.update(copy.deepcopy(fields))
    return result


def _require_base64_source(schema: Dict[str, Any]) -> None:
    """Make base64_data mandatory when local file sources are unavailable."""
    schema.pop("oneOf", None)
    required = [field for field in schema.get("required", []) if field != "file_path"]
    if "base64_data" not in required:
        required.append("base64_data")
    schema["required"] = required


def _without_file_path(tool: Dict[str, Any]) -> Dict[str, Any]:
    """Copy one tool without advertising a server-local file source."""
    result = copy.deepcopy(tool)
    result["description"] = _NETWORKED_TOOL_DESCRIPTIONS[tool["name"]]
    schema = result["inputSchema"]
    schema["properties"].pop("file_path", None)
    if tool["name"] == "import_profile":
        schema["required"] = ["profile"]
        return result
    if tool["name"] == "upload_images":
        item = schema["properties"]["images"]["items"]
        item["properties"].pop("file_path", None)
        _require_base64_source(item)
    else:
        _require_base64_source(schema)
    return result


def live_tool_definitions(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return a detached manifest matching this process's file-source policy."""
    if local_files_enabled():
        return copy.deepcopy(tools)
    return [
        _without_file_path(tool) if tool["name"] in _LOCAL_FILE_TOOL_NAMES else copy.deepcopy(tool)
        for tool in tools
    ]


def ordered_mcp_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return stable discovery order with compatible core tools first."""
    definitions = live_tool_definitions(tools)
    by_name = {tool["name"]: tool for tool in definitions}
    core = [by_name[name] for name in MCP_CORE_TOOL_NAMES]
    advanced = [tool for tool in definitions if tool["name"] not in MCP_CORE_TOOL_NAMES]
    return core + advanced


def mcp_tools_page(cursor: Any, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build one paginated tools/list result using an opaque cursor."""
    offset = 0
    if cursor not in (None, ""):
        if not isinstance(cursor, str) or not cursor.startswith(MCP_TOOL_CURSOR_PREFIX):
            raise ValueError("Некорректный cursor для tools/list")
        raw_offset = cursor[len(MCP_TOOL_CURSOR_PREFIX):]
        if not raw_offset.isdigit():
            raise ValueError("Некорректный cursor для tools/list")
        offset = int(raw_offset)

    definitions = ordered_mcp_tools(tools)
    if offset < 0 or offset > len(definitions):
        raise ValueError("Cursor tools/list указывает за пределы списка инструментов")

    end = min(offset + MCP_TOOL_PAGE_SIZE, len(definitions))
    result: Dict[str, Any] = {"tools": definitions[offset:end]}
    if end < len(definitions):
        result["nextCursor"] = f"{MCP_TOOL_CURSOR_PREFIX}{end}"
    return result
