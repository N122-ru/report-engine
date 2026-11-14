"""Convert editable DOCX content into the report editor's Markdown format."""

from __future__ import annotations

import io
import os
import re
import base64
import binascii
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from .image_input import MAX_BASE64_IMAGE_LENGTH, MAX_IMAGE_SIZE, validate_image_data


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_IMAGE_MARKER = "\ue000DOCX_IMAGE_{index}\ue001"
_FORMULA_PLACEHOLDER = "[Формула: OMML не преобразована в LaTeX]"


def _body_items(document: Document) -> Iterable[Paragraph | Table]:
    """Yield top-level paragraphs and tables in their document order."""
    for element in document.element.body.iterchildren():
        if element.tag == qn("w:p"):
            yield Paragraph(element, document)
        elif element.tag == qn("w:tbl"):
            yield Table(element, document)


def _safe_unique_name(filename: str, used: set[str]) -> str:
    """Return a sanitized, unused attachment name."""
    base = os.path.basename(filename.replace("\\", "/")).strip()
    safe = re.sub(r"[^\w.\-]", "_", base, flags=re.UNICODE)
    if not safe or safe.startswith("."):
        safe = "image.png"
    if safe not in used:
        used.add(safe)
        return safe
    stem, extension = os.path.splitext(safe)
    index = 2
    while f"{stem}_{index}{extension}" in used:
        index += 1
    unique = f"{stem}_{index}{extension}"
    used.add(unique)
    return unique


def _generic_image_alt(value: str) -> bool:
    """Identify Word-generated names that are not useful figure captions."""
    normalized = value.strip().casefold()
    return (
        not normalized
        or normalized in {"image", "picture", "рисунок", "иллюстрация", "фото"}
        or re.fullmatch(r"(?:image|picture|рисунок|иллюстрация)[ _-]?\d+", normalized) is not None
        or re.search(r"\.(?:png|jpe?g|gif|webp|bmp)$", normalized) is not None
    )


def _figure_caption(text: str) -> tuple[str, str] | None:
    """Extract figure number and title from a standalone caption paragraph."""
    match = re.fullmatch(
        r"(?:рисунок|рис\.?)\s+(\d+(?:\.\d+)*)\s*(?:[—–:-]\s*(.*))?",
        text.strip().rstrip("."),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    title = (match.group(2) or "").strip()
    return match.group(1), title


def _plain_text(paragraph: Paragraph) -> str:
    """Return paragraph text without drawing and formula markers."""
    return " ".join(paragraph.text.split())


def _run_markdown(run: Run) -> str:
    """Preserve the small subset of run formatting useful in Markdown."""
    text = run.text or ""
    if not text:
        return ""
    text = text.replace("\t", "    ").replace("\r", "").replace("\n", "\n").replace("\u00a0", " ")
    if run.bold and run.italic:
        return f"***{text}***"
    if run.bold:
        return f"**{text}**"
    if run.italic:
        return f"*{text}*"
    return text


def _drawing_image(
    paragraph: Paragraph,
    drawing: Any,
    used_names: set[str],
    warnings: list[str],
    image_index: int,
) -> dict[str, Any] | None:
    """Extract one embedded image from a Word drawing element."""
    blip = next((node for node in drawing.iter() if node.tag == qn("a:blip")), None)
    if blip is None:
        return None
    relationship_id = blip.get(qn("r:embed"))
    if not relationship_id:
        return None
    image_part = paragraph.part.related_parts.get(relationship_id)
    if image_part is None:
        warnings.append("Изображение из DOCX не имеет связанного media-файла и пропущено.")
        return None
    data = image_part.blob
    original_name = os.path.basename(str(image_part.partname)) or f"image_{image_index}.png"
    name = _safe_unique_name(original_name, used_names)
    try:
        validate_image_data(data)
    except ValueError:
        warnings.append(f"Изображение «{name}» имеет неподдерживаемый формат и пропущено.")
        return None

    alt = ""
    for node in drawing.iter():
        if node.tag == qn("wp:docPr"):
            alt = (node.get("descr") or node.get("name") or "").strip()
            break
    return {"filename": name, "data": data, "alt": alt or original_name}


def _paragraph_parts(
    paragraph: Paragraph,
    used_names: set[str],
    warnings: list[str],
    image_counter: list[int],
) -> tuple[str, list[dict[str, Any]]]:
    """Read text, drawings, and OMML in their original paragraph order."""
    parts: list[str] = []
    images: list[dict[str, Any]] = []
    for child in paragraph._p.iterchildren():
        if child.tag == qn("w:r"):
            run = Run(child, paragraph)
            drawings = [node for node in child.iter() if node.tag == qn("w:drawing")]
            if drawings:
                for drawing in drawings:
                    image_counter[0] += 1
                    image = _drawing_image(
                        paragraph, drawing, used_names, warnings, image_counter[0]
                    )
                    if image is None:
                        parts.append(f"[ Иллюстрация: image_{image_counter[0]} ]")
                    else:
                        image["marker"] = _IMAGE_MARKER.format(index=len(images))
                        images.append(image)
                        parts.append(image["marker"])
                # A drawing run normally has no text, but retain any text that
                # a producer placed before or after the drawing.
                text = _run_markdown(run)
                if text:
                    parts.append(text)
            else:
                parts.append(_run_markdown(run))
        elif child.tag == qn("w:hyperlink"):
            parts.append("".join(node.text or "" for node in child.iter() if node.tag == qn("w:t")))
        elif child.tag in {qn("m:oMath"), qn("m:oMathPara")}:
            parts.append(_FORMULA_PLACEHOLDER)
            warnings.append(
                "Формула OMML обнаружена, но в проекте нет конвертера OMML→LaTeX; "
                "на её месте оставлена честная пометка."
            )
        elif child.tag == qn("w:bookmarkStart") or child.tag == qn("w:bookmarkEnd"):
            continue
    return "".join(parts), images


def _list_info(paragraph: Paragraph, document: Document) -> tuple[str, int] | None:
    """Read numbering properties and resolve whether they are ordered."""
    num_pr = paragraph._p.pPr.find(qn("w:numPr")) if paragraph._p.pPr is not None else None
    if num_pr is None:
        text = paragraph.text
        visible_ordered = re.match(r"^(\d+)[.)](?:\s|\u00a0)", text)
        if visible_ordered:
            return "ordered", 0
        if re.match(r"^[–—-](?:\s|\u00a0)", text):
            return "bullet", 0
        return None

    ilvl_node = num_pr.find(qn("w:ilvl"))
    num_id_node = num_pr.find(qn("w:numId"))
    level = int(ilvl_node.get(qn("w:val"), "0")) if ilvl_node is not None else 0
    num_id = num_id_node.get(qn("w:val"), "") if num_id_node is not None else ""
    kind = "bullet"
    numbering = getattr(getattr(document.part, "numbering_part", None), "element", None)
    if numbering is not None and num_id:
        num = next((node for node in numbering.iter(qn("w:num")) if node.get(qn("w:numId")) == num_id), None)
        abstract_id = num.find(qn("w:abstractNumId")).get(qn("w:val")) if num is not None else None
        abstract = next(
            (node for node in numbering.iter(qn("w:abstractNum")) if node.get(qn("w:abstractNumId")) == abstract_id),
            None,
        )
        if abstract is not None:
            level_node = next(
                (node for node in abstract.iter(qn("w:lvl")) if node.get(qn("w:ilvl")) == str(level)),
                None,
            )
            fmt = level_node.find(qn("w:numFmt")) if level_node is not None else None
            if fmt is not None and fmt.get(qn("w:val"), "bullet") != "bullet":
                kind = "ordered"
    return kind, level


def _strip_visible_list_prefix(text: str, kind: str | None) -> str:
    """Remove a numbering glyph that Word rendered as ordinary text."""
    if kind == "ordered":
        return re.sub(r"^\d+[.)](?:\s|\u00a0)+", "", text, count=1)
    if kind == "bullet":
        return re.sub(r"^[–—-](?:\s|\u00a0)+", "", text, count=1)
    return text


def _parse_paragraph(
    paragraph: Paragraph,
    document: Document,
    used_names: set[str],
    warnings: list[str],
    image_counter: list[int],
) -> dict[str, Any]:
    """Build an intermediate paragraph record before title/caption filtering."""
    text, images = _paragraph_parts(paragraph, used_names, warnings, image_counter)
    plain = _plain_text(paragraph)
    list_data = _list_info(paragraph, document)
    list_kind = list_data[0] if list_data else None
    list_items: list[str] | None = None
    if list_kind:
        text = _strip_visible_list_prefix(text, list_kind)
        plain = _strip_visible_list_prefix(plain, list_kind).strip()
        has_num_pr = paragraph._p.pPr is not None and paragraph._p.pPr.find(qn("w:numPr")) is not None
        if not has_num_pr:
            separator = r"\s+\d+[.)](?:\s|\u00a0)+" if list_kind == "ordered" else r"\s+[–—-](?:\s|\u00a0)+"
            split_items = [item.strip() for item in re.split(separator, text.strip()) if item.strip()]
            if len(split_items) > 1:
                list_items = split_items
    style_name = getattr(getattr(paragraph, "style", None), "name", "") or ""
    heading_level: int | None = None
    style_match = re.fullmatch(r"Heading\s*([1-3])", style_name, flags=re.IGNORECASE)
    if style_match and plain:
        heading_level = int(style_match.group(1))
    else:
        ppr = paragraph._p.pPr
        keep_next = ppr is not None and ppr.find(qn("w:keepNext")) is not None
        keep_lines = ppr is not None and ppr.find(qn("w:keepLines")) is not None
        meaningful_runs = [run for run in paragraph.runs if run.text and run.text.strip()]
        conservative_bold = (
            not list_data
            and len(plain) <= 200
            and keep_next
            and keep_lines
            and bool(meaningful_runs)
            and all(run.bold for run in meaningful_runs)
            and not re.search(r"[.!?]$", plain)
        )
        if conservative_bold:
            heading_level = 1
    return {
        "kind": "paragraph",
        "text": text,
        "plain": plain,
        "images": images,
        "list": list_data,
        "list_items": list_items,
        "heading_level": heading_level,
        "source": paragraph,
        "skip": False,
    }


def _cell_text(
    cell: Any,
    document: Document,
    used_names: set[str],
    warnings: list[str],
    image_counter: list[int],
) -> tuple[str, list[dict[str, Any]]]:
    """Flatten a table cell while retaining paragraph line breaks."""
    # Table header emphasis is represented by Markdown's header row itself;
    # retaining Word's bold markers would make the imported table needlessly
    # noisy and would not preserve the cell's literal value.
    values: list[str] = []
    images: list[dict[str, Any]] = []
    for paragraph in cell.paragraphs:
        text, paragraph_images = _paragraph_parts(paragraph, used_names, warnings, image_counter)
        if text.strip():
            values.append(text.replace("**", "").strip().replace("\u00a0", " "))
        images.extend(paragraph_images)
    return "<br>".join(values).replace("|", "\\|"), images


def _table_record(
    table: Table,
    used_names: set[str],
    warnings: list[str],
    image_counter: list[int],
) -> dict[str, Any]:
    """Convert a Word table to a Markdown table intermediate record."""
    rows: list[list[str]] = []
    images: list[dict[str, Any]] = []
    for row in table.rows:
        values: list[str] = []
        for cell in row.cells:
            value, cell_images = _cell_text(cell, table._parent, used_names, warnings, image_counter)
            values.append(value)
            images.extend(cell_images)
        rows.append(values)
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    return {"kind": "table", "rows": rows, "images": images, "source": table, "skip": False}


def _table_is_signature(table: Table) -> bool:
    """Detect the title-page teacher/student signature table."""
    text = " ".join(cell.text for row in table.rows for cell in row.cells)
    return bool(re.search(r"\b(?:преподавател[ьи]|студент[ыа])\b", text, flags=re.IGNORECASE))


def _person_from_row(cells: list[str], kind: str) -> dict[str, str] | None:
    """Read one compact teacher or student row from the title table."""
    meaningful = [cell.strip() for cell in cells]
    if not meaningful or all(not cell or cell.startswith("(") for cell in meaningful):
        return None
    fio = meaningful[-1] if meaningful and not meaningful[-1].startswith("(") else ""
    if not fio or fio.casefold() in {"преподаватель", "преподаватели", "студент", "студенты"}:
        return None
    if kind == "teacher":
        role = meaningful[1] if len(meaningful) > 1 and meaningful[1] and not meaningful[1].startswith("(") else "ст. преп."
        return {"fio": fio, "role": role}
    group = meaningful[1] if len(meaningful) > 1 and meaningful[1] and not meaningful[1].startswith("(") else ""
    return {"fio": fio, "group": group}


def _title_hints(
    blocks: list[dict[str, Any]],
    document: Document,
) -> tuple[dict[str, Any], int | None]:
    """Recognize stable title markers and return the last title block index."""
    paragraph_records = [
        (index, block)
        for index, block in enumerate(blocks)
        if block["kind"] == "paragraph" and block["plain"]
    ]
    texts = [block["plain"] for _, block in paragraph_records]
    hints: dict[str, Any] = {}
    work_index: int | None = None
    for position, (index, block) in enumerate(paragraph_records):
        text = block["plain"]
        match = re.fullmatch(
            r"((?:о|по)\s+.+?работ(?:а|ы)?)(?:\s*№\s*(\d+))?",
            text.strip().rstrip("."),
            flags=re.IGNORECASE,
        )
        has_report_marker = any(
            re.fullmatch(r"ОТЧ[ЕЁ]Т.*", value, flags=re.IGNORECASE)
            for value in texts[: position + 1]
        )
        if match and (index == 0 or has_report_marker):
            hints["work_type"] = match.group(1).strip()
            if match.group(2):
                hints["work_number"] = int(match.group(2))
            work_index = index
            break
    if work_index is None:
        combined = "\n".join(texts[:20])
        match = re.search(
            r"ОТЧ[ЕЁ]Т.*?\n\s*((?:о|по)\s+.+?работ(?:а|ы)?)(?:\s*№\s*(\d+))?",
            combined,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            hints["work_type"] = match.group(1).strip()
            if match.group(2):
                hints["work_number"] = int(match.group(2))

    for _, block in paragraph_records:
        text = block["plain"].strip()
        if re.fullmatch(r"[«\"].+[»\"]", text) and len(text) <= 300:
            hints["work_theme"] = text[1:-1].strip()
            break
    discipline_match = re.search(r"по\s+дисциплине\s+[«\"](.+?)[»\"]", "\n".join(texts[:30]), flags=re.IGNORECASE)
    if discipline_match:
        hints["discipline"] = discipline_match.group(1).strip()

    teachers: list[dict[str, str]] = []
    students: list[dict[str, str]] = []
    active_kind: str | None = None
    signature_index: int | None = None
    for index, block in enumerate(blocks):
        if block["kind"] != "table":
            continue
        table = block["source"]
        if not _table_is_signature(table):
            continue
        signature_index = index
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            label = cells[0].casefold() if cells else ""
            if "преподавател" in label:
                active_kind = "teacher"
            elif "студент" in label:
                active_kind = "student"
            if active_kind == "teacher":
                person = _person_from_row(cells, active_kind)
                if person:
                    teachers.append(person)
            elif active_kind == "student":
                person = _person_from_row(cells, active_kind)
                if person:
                    students.append(person)
        break
    if teachers:
        hints["teachers"] = teachers
    if students:
        hints["students"] = students

    footer_texts = [
        paragraph.text.strip()
        for section in document.sections
        for footer in (section.first_page_footer, section.footer)
        for paragraph in footer.paragraphs
        if paragraph.text.strip()
    ]
    for footer_text in reversed(footer_texts):
        city_match = re.fullmatch(r"(.+?)\s+((?:19|20)\d{2})", footer_text)
        if city_match:
            hints["city"] = re.sub(r"^г(?:\.|\s)+\s*", "", city_match.group(1).strip(), flags=re.IGNORECASE)
            hints["year"] = int(city_match.group(2))
            break

    city_index: int | None = None
    for index, block in paragraph_records:
        city_match = re.fullmatch(r"(.+?)\s+((?:19|20)\d{2})", block["plain"].strip())
        if not city_match:
            continue
        city = re.sub(r"^г(?:\.|\s)+\s*", "", city_match.group(1).strip(), flags=re.IGNORECASE)
        if city and not re.search(r"\b(?:отч[её]т|работа|дисциплина)\b", city, flags=re.IGNORECASE):
            hints.setdefault("city", city)
            hints.setdefault("year", int(city_match.group(2)))
            city_index = index
            break

    has_report_heading = any(
        re.fullmatch(r"ОТЧ[ЕЁ]Т.*", value, flags=re.IGNORECASE) for value in texts[:10]
    )
    recognized = bool(
        hints.get("work_type")
        and (
            hints.get("discipline")
            or hints.get("work_theme")
            or hints.get("teachers")
            or hints.get("students")
            or has_report_heading
        )
    )
    if not recognized:
        return {}, None
    title_end = signature_index
    if city_index is not None and (title_end is None or city_index > title_end):
        title_end = city_index
    if title_end is None:
        candidates = [index for index, _ in paragraph_records if index <= (work_index or 0)]
        discipline_indices = [index for index, block in paragraph_records if "по дисциплине" in block["plain"].casefold()]
        if discipline_indices:
            candidates.append(discipline_indices[0])
        title_end = max(candidates or [0])
    return hints, title_end


def _render_paragraph(block: dict[str, Any], list_counters: dict[tuple[str, int], int]) -> str:
    """Render one intermediate paragraph as Markdown."""
    text = block["text"]
    for image in block["images"]:
        alt = image.get("alt", "")
        text = text.replace(image["marker"], f"![{alt}]({image['filename']})")
    if block["heading_level"] and block["plain"]:
        return f"{'#' * block['heading_level']} {block['plain']}"
    list_data = block["list"]
    if list_data:
        kind, level = list_data
        key = (kind, level)
        values = block.get("list_items") or [text.strip()]
        rendered: list[str] = []
        for value in values:
            if kind == "ordered":
                list_counters[key] += 1
                marker = f"{list_counters[key]}."
            else:
                marker = "-"
            rendered.append(f"{'  ' * level}{marker} {value}")
        return "\n".join(rendered)
    return text.strip()


def _render_table(block: dict[str, Any]) -> str:
    """Render a table record with a Markdown header separator."""
    rows = [list(row) for row in block["rows"]]
    for image in block.get("images", []):
        replacement = f"![{image.get('alt', '')}]({image['filename']})"
        rows = [[cell.replace(image["marker"], replacement) for cell in row] for row in rows]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(normalized[0]) + " |", "| " + " | ".join("---" for _ in range(width)) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in normalized[1:])
    return "\n".join(lines)


def parse_docx(document: Document, *, reserved_names: set[str] | None = None) -> dict[str, Any]:
    """Parse a python-docx document into Markdown and import metadata."""
    used_names = set(reserved_names or ())
    warnings: list[str] = []
    image_counter = [0]
    blocks: list[dict[str, Any]] = []
    for item in _body_items(document):
        if isinstance(item, Paragraph):
            blocks.append(_parse_paragraph(item, document, used_names, warnings, image_counter))
        else:
            blocks.append(_table_record(item, used_names, warnings, image_counter))

    hints, title_end = _title_hints(blocks, document)
    if not hints:
        warnings.append("Титульный лист не распознан полностью; реквизиты не изменены.")
    elif title_end is not None:
        for block in blocks[: title_end + 1]:
            block["skip"] = True

    # Move a standalone figure caption into the neighboring image alt text.
    for index, block in enumerate(blocks):
        if block["kind"] != "paragraph" or block["images"] or block["skip"]:
            continue
        caption = _figure_caption(block["plain"])
        if not caption:
            continue
        neighbor = next(
            (
                blocks[j]
                for j in (index + 1, index - 1)
                if 0 <= j < len(blocks)
                and blocks[j]["kind"] == "paragraph"
                and blocks[j]["images"]
                and not blocks[j]["skip"]
            ),
            None,
        )
        if neighbor and neighbor["kind"] == "paragraph" and neighbor["images"] and not neighbor["skip"]:
            for image in neighbor["images"]:
                if _generic_image_alt(image.get("alt", "")):
                    image["alt"] = caption[1] or image.get("alt", "")
            block["skip"] = True

    rendered: list[str] = []
    list_counters: defaultdict[tuple[str, int], int] = defaultdict(int)
    for block in blocks:
        if block["skip"]:
            continue
        value = _render_table(block) if block["kind"] == "table" else _render_paragraph(block, list_counters)
        if value.strip():
            rendered.append(value.strip())
    markdown = "\n\n".join(rendered).strip()
    uploaded = [
        {"filename": image["filename"], "data": image["data"], "size_bytes": len(image["data"])}
        for block in blocks
        for image in block.get("images", [])
    ]
    return {
        "markdown": markdown,
        "uploaded_images": [
            {key: value for key, value in image.items() if key != "data" and key != "marker"}
            for image in uploaded
        ],
        "meta_hints": hints,
        "warnings": list(dict.fromkeys(warnings)),
        "_image_data": uploaded,
    }


def parse_docx_bytes(data: bytes, *, reserved_names: set[str] | None = None) -> dict[str, Any]:
    """Parse DOCX bytes without writing the source document to disk."""
    if not isinstance(data, bytes) or not data:
        raise ValueError("Файл DOCX пуст")
    if len(data) > MAX_IMAGE_SIZE:
        raise ValueError(f"Размер файла DOCX превышает лимит {MAX_IMAGE_SIZE // (1024 * 1024)} МБ")
    return parse_docx(Document(io.BytesIO(data)), reserved_names=reserved_names)


def read_docx_path(path: str, *, max_size: int = MAX_IMAGE_SIZE) -> bytes:
    """Read one local DOCX file with the image-sized memory limit."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Параметр file_path должен быть непустой строкой")
    target = Path(path).expanduser()
    try:
        size = target.stat().st_size
        if size > max_size:
            raise ValueError(f"Размер файла DOCX превышает лимит {max_size // (1024 * 1024)} МБ")
        data = target.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("Файл DOCX не найден") from exc
    except OSError as exc:
        raise ValueError("Не удалось прочитать файл DOCX") from exc
    if len(data) > max_size:
        raise ValueError(f"Размер файла DOCX превышает лимит {max_size // (1024 * 1024)} МБ")
    return data


def decode_docx_data(encoded: str) -> bytes:
    """Decode bounded base64 DOCX input from an MCP call."""
    if not isinstance(encoded, str) or not encoded.strip():
        raise ValueError("Параметр base64_data должен быть непустой строкой")
    normalized = encoded.strip()
    if "base64," in normalized[:64].lower():
        normalized = normalized.split(",", 1)[1]
    if len(normalized) > MAX_BASE64_IMAGE_LENGTH:
        raise ValueError(f"Закодированный файл DOCX превышает лимит {MAX_IMAGE_SIZE // (1024 * 1024)} МБ")
    try:
        data = base64.b64decode(normalized, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"Некорректные данные DOCX: {exc}") from exc
    if not data or len(data) > MAX_IMAGE_SIZE:
        raise ValueError(f"Размер файла DOCX превышает лимит {MAX_IMAGE_SIZE // (1024 * 1024)} МБ")
    return data


def load_docx_input(args: dict[str, Any], *, allow_file_path: bool) -> bytes:
    """Load exactly one DOCX source for an MCP transport."""
    encoded = args.get("base64_data")
    file_path = args.get("file_path")
    if (encoded is None) == (file_path is None):
        raise ValueError("Передайте base64_data или file_path, но не оба параметра")
    if encoded is not None:
        return decode_docx_data(encoded)
    if not allow_file_path:
        raise ValueError(
            "Чтение файлов на машине сервера доступно только в автономных сборках; "
            "передайте DOCX через base64_data"
        )
    return read_docx_path(file_path)
