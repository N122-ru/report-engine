"""Locate the canonical core and allowlisted references in source and frozen runtimes."""

import sys
from pathlib import Path

from .image_input import MAX_IMAGE_SIZE, MAX_IMAGES_COUNT
from .pdf_converter import pdf_export_status
from .report_safety import MAX_MARKDOWN_BYTES

REFERENCE_NAMES = ("figures", "formulas", "tables", "style", "literals")
CONTRACT_VERSION = "1.2"
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
    return {
        "transport": transport, "contract_version": CONTRACT_VERSION,
        **pdf_export_status(), "file_path": True,
        "limits": {"image_bytes": MAX_IMAGE_SIZE, "images_count": MAX_IMAGES_COUNT,
                   "markdown_bytes": MAX_MARKDOWN_BYTES},
        "reference_resources": [resource["uri"] for resource in reference_resources()],
        "tools_diff": tools_diff,
    }
