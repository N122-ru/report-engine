"""Transport-free, in-memory report state for the local MCP runtime."""

import hashlib
import json
import mimetypes
import re
import os
import base64
import binascii
from urllib.parse import unquote
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

from ..models.report import ReportMetadata
from .generator import build_docx_report
from .linter import lint_docx_document
from .pdf_converter import convert_docx_to_pdf
from .markdown_parser import _image_size
from .typography import apply_typography_rules, strip_trailing_dot
from .profile import profile_metadata, validate_profile
from .image_input import MAX_IMAGE_SIZE, MAX_IMAGES_COUNT
from .report_safety import MAX_MARKDOWN_BYTES, ReportVerification, add_content_guards, report_digest, validate_detail

# BMP is not supported; WebP is checked separately by its RIFF container.
IMAGE_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class HeadlessReport:
    def __init__(self, output_dir: Path):
        try:
            self.output_dir = Path(output_dir).expanduser().resolve(strict=True)
        except OSError as exc:
            raise ValueError("Папка экспорта должна существовать") from exc
        if not self.output_dir.is_dir():
            raise ValueError("Путь экспорта должен указывать на папку")
        self.metadata: ReportMetadata | None = None
        self.content = ""
        self.images: dict[str, bytes] = {}
        self.image_hashes: dict[str, str] = {}
        self.verification = ReportVerification()

    def _require_report(self) -> ReportMetadata:
        if self.metadata is None:
            raise ValueError("Сначала создайте отчёт через create_report")
        return self.metadata

    def _revisions(self) -> dict[str, str]:
        metadata = self._require_report().model_dump()
        return {
            "revision": _digest(self.content),
            "meta_revision": _digest(json.dumps(metadata, ensure_ascii=False, sort_keys=True)),
            "image_revision": _digest(json.dumps(self.image_hashes, sort_keys=True)),
        }

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        if not isinstance(filename, str):
            raise ValueError("Имя изображения должно быть строкой")
        base = os.path.basename(filename.replace("\\", "/")).strip()
        safe_name = re.sub(r"[^\w.\-]", "_", base, flags=re.UNICODE)
        if not safe_name or safe_name.startswith(".") or safe_name in {".", ".."}:
            raise ValueError("Укажите безопасное имя изображения")
        if len(safe_name) > 128:
            raise ValueError("Имя изображения слишком длинное")
        return safe_name

    @staticmethod
    def _validate_image_data(data: bytes) -> None:
        if not isinstance(data, bytes) or not data:
            raise ValueError("Данные изображения пусты")
        if len(data) > MAX_IMAGE_SIZE:
            raise ValueError(f"Размер изображения превышает {MAX_IMAGE_SIZE // (1024 * 1024)} МБ")
        valid_signature = data.startswith(IMAGE_SIGNATURES) or (
            data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP"
        )
        if not valid_signature:
            raise ValueError("Данные не похожи на поддерживаемое изображение")

    def list_images(self) -> list[dict[str, Any]]:
        self._require_report()
        used_names = set()
        for token in MarkdownIt("commonmark").parse(self.content):
            if token.type != "inline" or not token.children:
                continue
            for child in token.children:
                if child.type == "image":
                    src = unquote(child.attrGet("src") or "")
                    used_names.add(os.path.basename(src.replace("\\", "/")))
        result = []
        for filename, data in self.images.items():
            dimensions = _image_size(data)
            result.append({
                "filename": filename,
                "size_bytes": len(data),
                "sha256": self.image_hashes[filename],
                "mime_type": mimetypes.guess_type(filename)[0] or "image/png",
                "width_px": dimensions[0] if dimensions else None,
                "height_px": dimensions[1] if dimensions else None,
                "is_in_report": filename in used_names,
            })
        return result

    def get_image(self, filename: str) -> bytes:
        safe_name = self._sanitize_filename(filename)
        try:
            return self.images[safe_name]
        except KeyError as exc:
            raise ValueError(f"Изображение «{safe_name}» не найдено") from exc

    def upload_image(
        self,
        filename: str,
        data: bytes,
        expected_image_revision: str,
        *,
        caption: str = "",
        insert_into_report: bool = False,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        """Upload one image under the current image and optional text revisions."""
        self._require_report()
        self._check_revision("image_revision", expected_image_revision)
        if insert_into_report:
            if expected_revision is None:
                raise ValueError("Вставка изображения требует revision текста")
            self._check_revision("revision", expected_revision)
        self._store_image(filename, data, caption, insert_into_report)
        return self._revisions()

    def _store_image(self, filename: str, data: bytes, caption: str, insert_into_report: bool) -> str:
        """Validate and store one image without repeating batch revision checks."""
        safe_name = self._sanitize_filename(filename)
        self._validate_image_data(data)
        if safe_name in self.images:
            raise ValueError(f"Изображение «{safe_name}» уже прикреплено")
        if len(self.images) >= MAX_IMAGES_COUNT:
            raise ValueError("Превышено максимальное число изображений")
        next_content = self.content
        if insert_into_report:
            clean_caption = caption.strip() or "Иллюстрация"
            next_content = self.content.rstrip() + f"\n\n![{clean_caption}]({safe_name})\n"
            if len(next_content.encode("utf-8")) > MAX_MARKDOWN_BYTES:
                raise ValueError("Размер текста отчёта превышает 500 КБ")
        self.images[safe_name] = data
        self.image_hashes[safe_name] = hashlib.sha256(data).hexdigest()
        self.content = next_content
        self.verification.changed()
        return safe_name

    def upload_images(
        self, images: list[dict[str, Any]], expected_image_revision: str,
        *, expected_revision: str | None = None,
    ) -> dict[str, Any]:
        """Upload valid items sequentially, collecting per-item validation errors.

        Revisions are checked once before any write. Input errors captured at
        the transport boundary remain in the ordered results alongside core
        validation errors; successful uploads are not rolled back.
        """
        self._require_report()
        if not isinstance(images, list) or not 1 <= len(images) <= MAX_IMAGES_COUNT:
            raise ValueError(f"Ожидается от 1 до {MAX_IMAGES_COUNT} изображений")
        self._check_revision("image_revision", expected_image_revision)
        if any(isinstance(item, dict) and item.get("insert_into_report") for item in images):
            if expected_revision is None:
                raise ValueError("Вставка изображения требует revision текста")
            self._check_revision("revision", expected_revision)
        results = []
        for item in images:
            filename = item.get("filename") if isinstance(item, dict) else None
            try:
                if not isinstance(item, dict):
                    raise ValueError("Каждое изображение должно быть объектом")
                if "error" in item:
                    raise ValueError(item["error"])
                if not isinstance(item.get("caption", ""), str):
                    raise ValueError("Параметр caption должен быть строкой")
                if not isinstance(item.get("insert_into_report", False), bool):
                    raise ValueError("Параметр insert_into_report должен быть логическим значением")
                name = self._store_image(filename, item.get("data"), item.get("caption", ""),
                                         item.get("insert_into_report", False))
                results.append({"filename": name, "ok": True, "result": self._revisions()})
            except ValueError as exc:
                results.append({"filename": filename, "ok": False, "error": str(exc)})
        return {"uploaded_count": sum(item["ok"] for item in results),
                "results": results, **self._revisions()}

    def delete_image(self, filename: str, expected_image_revision: str) -> dict[str, Any]:
        self._require_report()
        self._check_revision("image_revision", expected_image_revision)
        safe_name = self._sanitize_filename(filename)
        if any(item["filename"] == safe_name and item["is_in_report"] for item in self.list_images()):
            raise ValueError("Сначала удалите ссылку на изображение из Markdown")
        if safe_name not in self.images:
            raise ValueError(f"Изображение «{safe_name}» не найдено")
        del self.images[safe_name]
        del self.image_hashes[safe_name]
        self.verification.changed()
        return self._revisions()

    def _check_revision(self, field: str, expected: str) -> None:
        if expected != self._revisions()[field]:
            raise ValueError("Конфликт версий: получите актуальное состояние отчёта")

    @staticmethod
    def _validate_metadata(metadata: dict[str, Any], *, allow_profile_logo: bool = False) -> ReportMetadata:
        if not isinstance(metadata, dict) or set(metadata) - ReportMetadata.model_fields.keys():
            raise ValueError("Переданы неизвестные реквизиты отчёта")
        if metadata.get("custom_logo") or metadata.get("logo_mode") == "custom":
            if not allow_profile_logo:
                raise ValueError("Пользовательский логотип пока не поддерживается в headless-режиме")
            logo = metadata.get("custom_logo")
            if not isinstance(logo, str) or not logo.startswith("data:image/") or ";base64," not in logo:
                raise ValueError("Профиль должен содержать пользовательский логотип как data-URL")
            try:
                encoded = logo.split(";base64,", 1)[1]
                decoded = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("Профиль содержит некорректный пользовательский логотип") from exc
            if not decoded or len(decoded) > 2 * 1024 * 1024:
                raise ValueError("Размер пользовательского логотипа превышает 2 МБ")
        if len(json.dumps(metadata, ensure_ascii=False).encode("utf-8")) > MAX_MARKDOWN_BYTES:
            raise ValueError("Размер реквизитов отчёта превышает 500 КБ")
        try:
            return ReportMetadata.model_validate(metadata, strict=True)
        except ValueError as exc:
            raise ValueError("Реквизиты отчёта не соответствуют схеме") from exc

    def create_report(self, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Create one in-memory report without replacing an existing report."""
        if self.metadata is not None:
            raise ValueError("Отчёт уже создан; новый отчёт требует нового процесса")
        self.metadata = self._validate_metadata({} if metadata is None else metadata)
        return self.get_report_state()

    def get_report_state(self, detail: str = "full") -> dict[str, Any]:
        """Return Markdown, metadata, and current report revisions."""
        validate_detail(detail)
        revisions = self._revisions()
        common = {**revisions, "verify_state": self.verification.state(revisions)}
        if detail == "digest":
            return common | report_digest(self.content, self.images)
        return {
            "markdown_content": self.content,
            "metadata": self._require_report().model_dump(),
            "images": self.list_images(),
            **common,
        }

    def update_meta(self, fields: dict[str, Any], expected_meta_revision: str) -> dict[str, Any]:
        """Update only the supplied metadata using a fresh meta_revision."""
        self._check_revision("meta_revision", expected_meta_revision)
        if not fields:
            raise ValueError("Не переданы реквизиты для обновления")
        metadata = self._validate_metadata({**self._require_report().model_dump(), **fields})
        if metadata != self.metadata:
            self.verification.changed()
        self.metadata = metadata
        return self._revisions()

    def import_profile(self, profile: dict[str, Any], expected_meta_revision: str | None = None) -> dict[str, Any]:
        """Import a portable profile, creating the in-memory report when needed."""
        validated = validate_profile(profile)
        if self.metadata is not None:
            if expected_meta_revision is None:
                raise ValueError("Импорт существующего отчёта требует meta_revision")
            self._check_revision("meta_revision", expected_meta_revision)
        metadata = profile_metadata(validated)
        updated = self._validate_metadata(metadata, allow_profile_logo=True)
        if updated != self.metadata:
            self.verification.changed()
        self.metadata = updated
        result = self.get_report_state()
        result["profile_subject"] = validated["subject"]
        return result

    def append_or_update_section(
        self, section_heading: str, section_content: str, expected_revision: str,
    ) -> dict[str, Any]:
        """Add a section or replace its body while preserving adjacent sections."""
        self._check_revision("revision", expected_revision)
        heading = section_heading.strip()
        if not re.fullmatch(r"#{1,6} [^\r\n]+", heading):
            raise ValueError("Заголовок должен быть одной строкой Markdown с #")
        parser = MarkdownIt("commonmark")
        headings = [t for t in parser.parse(self.content) if t.type == "heading_open" and t.map]
        lines = self.content.splitlines(keepends=True)
        matches = [i for i, token in enumerate(headings) if lines[token.map[0]].strip() == heading]
        if len(matches) > 1:
            raise ValueError("Заголовок неоднозначен: найдены несколько одинаковых разделов")
        replacement = f"{heading}\n\n{section_content.strip()}\n\n"
        if matches:
            index = matches[0]
            start = headings[index].map[0]
            end = headings[index + 1].map[0] if index + 1 < len(headings) else len(lines)
            updated = "".join(lines[:start]) + replacement + "".join(lines[end:])
        else:
            updated = self.content.rstrip() + ("\n\n" if self.content.strip() else "") + replacement
        if len(updated.encode("utf-8")) > MAX_MARKDOWN_BYTES:
            raise ValueError("Размер текста отчёта превышает 500 КБ")
        next_content = updated.rstrip() + "\n"
        if next_content != self.content:
            self.verification.changed()
        self.content = next_content
        return self._revisions()

    def autofix_typography(self, expected_revision: str) -> dict[str, Any]:
        self._check_revision("revision", expected_revision)
        fixed_lines = []
        in_code = False
        for line in self.content.split("\n"):
            if line.strip().startswith("```"):
                in_code = not in_code
                fixed_lines.append(line)
            elif in_code:
                fixed_lines.append(line)
            elif re.match(r"^#{1,6}\s+", line):
                fixed_lines.append(strip_trailing_dot(line))
            else:
                parts = re.split(r"(`[^`\n]*`)", line)
                fixed_lines.append("".join(
                    part if part.startswith("`") else apply_typography_rules(part)
                    for part in parts
                ))
        fixed = "\n".join(fixed_lines)
        if len(fixed.encode("utf-8")) > MAX_MARKDOWN_BYTES:
            raise ValueError("Размер текста отчёта превышает 500 КБ")
        if fixed != self.content:
            self.verification.changed()
        self.content = fixed
        return self._revisions()

    def lint_report(self) -> dict[str, Any]:
        """Validate the current report and advance the verification phase."""
        result = self._lint_result()
        self.verification.record_lint(self._revisions(), result)
        return result

    def _lint_result(self) -> dict[str, Any]:
        """Compute lint without changing workflow state for read-only reviews."""
        metadata = self._require_report()
        docx_buffer = build_docx_report(metadata, self.content, self.images)
        result = lint_docx_document(docx_buffer)
        return add_content_guards({
            "is_valid": result.is_valid,
            "status": result.status,
            "score": result.score,
            "errors": [item.model_dump() for item in result.errors],
            "warnings": [item.model_dump() for item in result.warnings],
            "metrics": result.metrics.model_dump() if result.metrics else {},
        }, self.content, self.images)

    def review_snapshot(self) -> dict[str, Any]:
        """Return a transferable report and lint snapshot without media bytes or mutation."""
        return self.get_report_state() | {"lint": self._lint_result()}

    def export_report(
        self, filename: str, expected_revision: str, expected_meta_revision: str,
        expected_image_revision: str, format: str | None = None,
        confirm_blocked_export: bool = False,
    ) -> dict[str, Any]:
        """Export a new DOCX or PDF to the allowed directory without overwriting."""
        for field, expected in (
            ("revision", expected_revision), ("meta_revision", expected_meta_revision),
            ("image_revision", expected_image_revision),
        ):
            self._check_revision(field, expected)
        self.verification.require_export(self._revisions(), confirm_blocked_export)
        if (
            not filename or len(filename) > 128 or filename.startswith(".")
            or filename != filename.strip() or re.search(r'[\\/:*?"<>|\x00-\x1f]', filename)
            or re.match(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", filename, re.I)
            or Path(filename).suffix.lower() not in {".docx", ".pdf"}
        ):
            raise ValueError("Укажите безопасное имя файла с расширением .docx или .pdf")
        output_format = (format or Path(filename).suffix.lstrip(".")).lower()
        if output_format not in {"docx", "pdf"} or Path(filename).suffix.lower() != f".{output_format}":
            raise ValueError("Формат экспорта должен соответствовать расширению файла")
        target = self.output_dir / filename
        if self.output_dir.resolve() != self.output_dir:
            raise ValueError("Папка экспорта изменилась")
        docx_data = build_docx_report(self._require_report(), self.content, self.images).getvalue()
        data = docx_data if output_format == "docx" else convert_docx_to_pdf(docx_data).getvalue()
        try:
            with target.open("xb") as output:
                output.write(data)
        except FileExistsError as exc:
            raise ValueError("Файл уже существует; выберите новое имя") from exc
        return {"path": str(target), "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
