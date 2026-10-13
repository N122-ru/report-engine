"""Optional DOCX-to-PDF conversion through a locally installed office CLI."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


PDF_DISABLED_ENV = "REPORT_ENGINE_DISABLE_PDF"
PDF_CONVERTER_ENV = "REPORT_ENGINE_PDF_CONVERTER"
RUNTIME_DIR_ENV = "REPORT_ENGINE_RUNTIME_DIR"
ConverterKind = Literal["office", "docbuilder"]


@dataclass(frozen=True)
class PdfConverter:
    kind: ConverterKind
    executable: str


def _runtime_dir() -> Path | None:
    configured = os.environ.get(RUNTIME_DIR_ENV, "").strip()
    if configured:
        path = Path(configured).expanduser().resolve()
        return path if path.is_dir() else None

    if getattr(sys, "frozen", False):
        path = Path(sys.executable).resolve().parent / "runtime"
        return path if path.is_dir() else None
    return None


def _converter_kind(executable: str) -> ConverterKind:
    return "docbuilder" if "docbuilder" in Path(executable).stem.casefold() else "office"


def _candidate_executables() -> list[PdfConverter]:
    candidates: list[PdfConverter] = []
    configured = os.environ.get(PDF_CONVERTER_ENV, "").strip()
    if configured:
        candidates.append(PdfConverter(_converter_kind(configured), configured))

    runtime_dir = _runtime_dir()
    if runtime_dir is not None:
        for name in ("soffice", "soffice.exe", "libreoffice", "libreoffice.exe", "docbuilder", "docbuilder.exe"):
            for candidate in (
                runtime_dir / "libreoffice" / "program" / name,
                runtime_dir / "libreoffice" / name,
                runtime_dir / "onlyoffice" / name,
            ):
                if candidate.is_file():
                    candidates.append(PdfConverter(_converter_kind(name), str(candidate)))

    for name in ("libreoffice", "soffice", "docbuilder"):
        executable = shutil.which(name)
        if executable:
            candidates.append(PdfConverter(_converter_kind(name), executable))
    return candidates


def _probe(converter: PdfConverter) -> bool:
    argument = "-v" if converter.kind == "docbuilder" else "--version"
    try:
        result = subprocess.run(
            [converter.executable, argument],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def detect_pdf_converter() -> PdfConverter | None:
    """Return the first locally installed converter that passes a cheap probe."""
    if os.environ.get(PDF_DISABLED_ENV, "").strip().casefold() in {"1", "true", "yes", "on"}:
        return None
    return next((candidate for candidate in _candidate_executables() if _probe(candidate)), None)


def pdf_export_status() -> dict[str, str | bool | None]:
    """Return the current PDF capability without making it a startup requirement."""
    converter = detect_pdf_converter()
    return {
        "pdf_export": converter is not None,
        "pdf_converter": converter.kind if converter else None,
    }


def pdf_export_enabled() -> bool:
    return bool(pdf_export_status()["pdf_export"])


def _font_directory() -> Path | None:
    runtime_dir = _runtime_dir()
    if runtime_dir is None:
        return None
    fonts = runtime_dir / "fonts"
    return fonts if fonts.is_dir() else None


def _font_environment(environment: dict[str, str], fonts: Path | None, temporary_dir: str) -> None:
    if fonts is None or os.name == "nt":
        return
    font_config = os.path.join(temporary_dir, "fonts.conf")
    escaped_fonts = str(fonts).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    with open(font_config, "w", encoding="utf-8") as config:
        config.write(
            "<?xml version=\"1.0\"?>"
            "<!DOCTYPE fontconfig SYSTEM \"fonts.dtd\">"
            f"<fontconfig><dir>{escaped_fonts}</dir>"
            "<include ignore_missing=\"yes\">/etc/fonts/fonts.conf</include></fontconfig>"
        )
    environment["FONTCONFIG_FILE"] = font_config


def _run_converter(converter: PdfConverter, docx_path: str, pdf_path: str, temporary_dir: str) -> None:
    environment = os.environ.copy()
    _font_environment(environment, _font_directory(), temporary_dir)
    if converter.kind == "docbuilder":
        script_path = os.path.join(temporary_dir, "convert.docbuilder")
        with open(script_path, "w", encoding="utf-8") as script:
            script.write(f"builder.OpenFile({json.dumps(docx_path)}, \"\");\n")
            script.write(f"builder.SaveFile(\"pdf\", {json.dumps(pdf_path)});\n")
            script.write("builder.CloseFile();\n")
        command = [converter.executable, script_path]
    else:
        profile_dir = os.path.join(temporary_dir, "profile")
        command = [
            converter.executable,
            f"-env:UserInstallation=file://{profile_dir}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            temporary_dir,
            docx_path,
        ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        env=environment,
        cwd=os.path.dirname(converter.executable) or None,
        check=False,
    )
    if result.returncode != 0:
        details = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Ошибка конвертации в PDF: {details}")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError("Сконвертированный PDF файл не найден")


def convert_docx_to_pdf(docx_bytes: bytes) -> io.BytesIO:
    """Convert DOCX bytes with a converter that was detected at request time."""
    converter = detect_pdf_converter()
    if converter is None:
        raise RuntimeError(
            "PDF недоступен: установите LibreOffice/OnlyOffice Document Builder "
            "или экспортируйте DOCX вручную в Office"
        )

    with tempfile.TemporaryDirectory() as temporary_dir:
        docx_path = os.path.join(temporary_dir, "document.docx")
        pdf_path = os.path.join(temporary_dir, "document.pdf")
        with open(docx_path, "wb") as document:
            document.write(docx_bytes)
        _run_converter(converter, docx_path, pdf_path, temporary_dir)
        return io.BytesIO(Path(pdf_path).read_bytes())
