"""Identify blocks in the current Markdown revision for targeted edits."""

import hashlib
from dataclasses import dataclass

from markdown_it import MarkdownIt

from .section_editor import sections


@dataclass(frozen=True)
class Block:
    id: str
    type: str
    start: int
    end: int
    start_line: int
    end_line: int
    preview: str


def blocks(markdown: str, revision: str) -> list[Block]:
    lines = markdown.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    result: list[Block] = []
    tokens = MarkdownIt("commonmark").parse(markdown)
    for index, token in enumerate(tokens):
        if not token.map:
            continue
        kind = None
        if token.type == "heading_open" and token.level == 0:
            kind = "heading"
        elif token.type == "paragraph_open" and token.level == 0:
            inline = tokens[index + 1] if index + 1 < len(tokens) else None
            children = inline.children if inline and inline.type == "inline" else []
            kind = "image" if any(c.type == "image" for c in (children or [])) else "paragraph"
        elif token.type == "list_item_open":
            kind = "task"
        elif token.type in ("fence", "code_block") and token.level == 0:
            kind = "code"
        if not kind:
            continue
        start_line, end_line = token.map
        start, end = offsets[start_line], offsets[end_line]
        snippet = markdown[start:end].strip()
        identifier = hashlib.sha256(f"{revision}:{start}:{end}:{kind}".encode()).hexdigest()[:20]
        result.append(Block(f"block:{identifier}", kind, start, end, start_line + 1, end_line, snippet[:110]))
    return result


def edit_block(markdown: str, revision: str, block_id: str, replacement: str | None) -> str:
    matches = [block for block in blocks(markdown, revision) if block.id == block_id]
    if len(matches) != 1:
        raise ValueError("Блок не найден в этой версии отчёта; получите новый outline")
    block = matches[0]
    if replacement is None and block.type == "heading":
        raise ValueError("Удаление заголовка оставит его содержимое без раздела")
    if replacement is not None and not replacement.strip():
        raise ValueError("Для удаления блока используйте delete_block")
    if replacement is None:
        left, right = markdown[:block.start], markdown[block.end:]
        return (left.rstrip("\n") + ("\n\n" if left and right else "") + right.lstrip("\n"))
    text = replacement.strip() + ("\n" if markdown[block.start:block.end].endswith("\n") else "")
    result = markdown[:block.start] + text + markdown[block.end:]
    old_headings = [section.heading for section in sections(markdown)]
    new_headings = [section.heading for section in sections(result)]
    if block.type != "heading" and old_headings != new_headings:
        raise ValueError("Правка блока меняет структуру разделов; используйте append_or_update_section")
    if block.type == "heading" and len(old_headings) != len(new_headings):
        raise ValueError("Правка заголовка меняет число разделов")
    return result


def move_figure(markdown: str, revision: str, block_id: str, before_block_id: str) -> str:
    by_id = {block.id: block for block in blocks(markdown, revision)}
    source, target = by_id.get(block_id), by_id.get(before_block_id)
    if source is None or source.type != "image" or target is None:
        raise ValueError("Получите действительные ID рисунка и целевого блока из get_document_outline")
    if source.id == target.id or source.end == target.start:
        return markdown
    image = markdown[source.start:source.end].strip("\n")
    if target.start < source.start:
        left = markdown[:target.start].rstrip("\n")
        between = markdown[target.start:source.start].strip("\n")
        tail = markdown[source.end:].lstrip("\n")
        result = (left + ("\n\n" if left else "") + image + "\n\n"
                  + between + ("\n\n" + tail if tail else "\n"))
    else:
        left = markdown[:source.start].rstrip("\n")
        between = markdown[source.end:target.start].strip("\n")
        tail = markdown[target.start:].lstrip("\n")
        result = (left + ("\n\n" if left else "") + between
                  + ("\n\n" if between else "") + image + "\n\n" + tail)
    if [s.heading for s in sections(markdown)] != [s.heading for s in sections(result)]:
        raise ValueError("Перемещение рисунка изменило структуру разделов")
    return result
