"""Edit Markdown sections safely while preserving adjacent blocks."""

import re
import hashlib
from dataclasses import dataclass

from markdown_it import MarkdownIt


@dataclass(frozen=True)
class Section:
    heading: str
    level: int
    start: int
    body_start: int
    end: int


def section_identifier(revision: str, start: int) -> str:
    return "section:" + hashlib.sha256(f"{revision}:{start}".encode()).hexdigest()[:20]


def sections(markdown: str) -> list[Section]:
    """Find heading boundaries outside lists, blockquotes, and code blocks."""
    lines = markdown.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    headings = []
    for token in MarkdownIt("commonmark").parse(markdown):
        if token.type == "heading_open" and token.map and token.level == 0:
            first, last = token.map
            headings.append((lines[first].strip(), int(token.tag[1:]), offsets[first], offsets[last]))
    result = []
    for index, (heading, level, start, body_start) in enumerate(headings):
        end = next((item[2] for item in headings[index + 1:] if item[1] <= level), len(markdown))
        result.append(Section(heading, level, start, body_start, end))
    return result


def edit_section(markdown: str, heading: str, content: str, mode: str,
                 section_id: str | None = None, revision: str | None = None) -> tuple[str, str]:
    """Return new Markdown and status without changing the source on failure."""
    heading = heading.strip()
    if not re.fullmatch(r"#{1,6}[ \t]+[^\n]+", heading):
        raise ValueError("section_heading должен быть одной строкой с Markdown-заголовком")
    if mode not in ("update_or_append", "replace", "append", "replace_body", "append_to_body"):
        raise ValueError(f"Неизвестный режим редактирования: {mode}")
    found = sections(markdown)
    matches = [s for s in found if s.heading == heading and (
        section_id is None or (revision is not None and section_identifier(revision, s.start) == section_id)
    )]
    if section_id and not matches:
        raise ValueError("Раздел с указанным ID не найден в этой версии документа")
    if len(matches) > 1:
        raise ValueError(f"Заголовок «{heading}» встречается несколько раз: уточните целевой раздел")
    if not matches:
        if mode != "update_or_append":
            raise ValueError(f"Раздел «{heading}» не найден; добавьте его явно через update_or_append")
        level = len(heading) - len(heading.lstrip("#"))
        if any(s.level <= level for s in sections(content)):
            raise ValueError("Тело раздела содержит заголовок того же или более высокого уровня")
        separator = "\n\n" if markdown.strip() else ""
        return markdown.rstrip() + separator + heading + "\n\n" + content.strip() + "\n", "appended"

    target = matches[0]
    # Allow nested headings only; peer or higher-level headings would change
    # the boundaries of adjacent sections.
    if any(s.level <= target.level for s in sections(content)):
        raise ValueError("Тело раздела содержит заголовок того же или более высокого уровня")
    if mode in ("append", "append_to_body"):
        old_body = markdown[target.body_start:target.end].strip()
        body = old_body + ("\n\n" if old_body and content.strip() else "") + content.strip()
    else:
        body = content.strip()
    suffix = "\n\n" if target.end < len(markdown) else "\n"
    # Append preserves original spacing after the heading; replacement uses
    # consistent spacing. Bytes outside [body_start:end] remain unchanged.
    if mode in ("append", "append_to_body"):
        leading = "\n" if markdown[target.body_start:target.end].startswith("\n") else ""
    else:
        leading = "\n"
    new_body = leading + body + suffix if body else suffix
    return markdown[:target.body_start] + new_body + markdown[target.end:], "updated"
