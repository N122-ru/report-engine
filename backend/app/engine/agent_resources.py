"""Locate the canonical core and allowlisted references in source and frozen runtimes."""

import sys
from pathlib import Path

from .image_input import MAX_IMAGE_SIZE, MAX_IMAGES_COUNT
from .pdf_converter import pdf_export_status
from .report_safety import MAX_MARKDOWN_BYTES

REFERENCE_NAMES = ("figures", "formulas", "tables", "style", "literals")
CONTRACT_VERSION = "1.1"


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
    return {
        "transport": transport, "contract_version": CONTRACT_VERSION,
        **pdf_export_status(), "file_path": True,
        "limits": {"image_bytes": MAX_IMAGE_SIZE, "images_count": MAX_IMAGES_COUNT,
                   "markdown_bytes": MAX_MARKDOWN_BYTES},
        "reference_resources": [resource["uri"] for resource in reference_resources()],
    }
