"""Render Markdown tokens as OpenXML document elements.

Support headings, listings, figures, tables, lists, and inline formatting
according to GOST 7.32-2017 / GOST 2.105-2019.
"""

import os
import re
from urllib.parse import unquote
from typing import Dict, Optional, Tuple
from markdown_it import MarkdownIt
from docx import Document
from docx.shared import Pt, Mm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn

from .oxml_utils import (
    set_cell_background,
    set_cell_margins,
    set_table_header_row,
    set_table_row_cant_split,
    set_table_gost_borders,
    set_listing_clean_borders,
    set_cell_no_borders
)
from .typography import (
    apply_typography_rules,
    clean_heading_text,
    clean_figure_caption,
    clean_table_caption,
    clean_listing_caption
)
from .math_utils import latex_to_omml, fallback_latex_to_unicode

def _extract_equation_and_number(raw_text: str) -> Tuple[str, Optional[str]]:
    r"""Extract a LaTeX equation body and its optional number.

    Supported forms:
    - $$formula \tag{1}$$
    - $$formula$$ (1)
    - $$formula \qquad (1)$$
    """
    raw = raw_text.strip()

    # Accept an external number after the closing math delimiter.
    m_outside = re.match(r'^\$\$(.*?)\$\$\s*(\((?:\d+(?:\.\d+)*|[а-яёА-ЯЁa-zA-Z0-9\.\-]+)\))$', raw, flags=re.DOTALL)
    if m_outside:
        return m_outside.group(1).strip(), m_outside.group(2).strip()

    if raw.startswith("$$") and raw.endswith("$$") and len(raw) > 4:
        body = raw[2:-2].strip()

        # Accept an internal LaTeX tag.
        m_tag = re.search(r'\\tag\{([^}]+)\}', body, flags=re.DOTALL)
        if m_tag:
            t_val = m_tag.group(1).strip()
            if not (t_val.startswith('(') and t_val.endswith(')')):
                t_val = f"({t_val})"
            clean = re.sub(r'\\tag\{[^}]+\}', '', body, flags=re.DOTALL).strip()
            return clean, t_val

        # Accept a number preceded by a LaTeX spacing command.
        m_quad = re.search(r'(?:\\qquad|\\quad|\s{3,})\s*(\((?:\d+(?:\.\d+)*)\))\s*$', body, flags=re.DOTALL)
        if m_quad:
            t_val = m_quad.group(1).strip()
            clean = body[:m_quad.start()].strip()
            return clean, t_val

        return body, None

    return raw, None


def _inline_plain_text(inline_tok) -> str:
    """Flatten inline tokens so Markdown delimiters do not leak into headings."""
    if inline_tok is None:
        return ""
    children = getattr(inline_tok, "children", None)
    if not children:
        return inline_tok.content or ""
    parts = []
    for c in children:
        if c.type in ("text", "code_inline"):
            parts.append(c.content)
        elif c.type == "image":
            parts.append(c.content)
        elif c.type in ("softbreak", "hardbreak"):
            parts.append(" ")
        # Skip strong/em/link wrappers: their contents have separate text tokens.
    return "".join(parts)


def _list_start_number(list_open_tok) -> int:
    """Read the list's start attribute, defaulting invalid values to one.

    Markdown-it supplies start for continued and interrupted lists.
    """
    try:
        attrs = dict(getattr(list_open_tok, "attrs", None) or {})
        return max(1, int(attrs.get("start", 1) or 1))
    except (TypeError, ValueError):
        return 1


def _explicit_figure_number(alt: str) -> Optional[str]:
    """Extract an author-supplied figure number from the caption prefix.

    Preserve compound numbers such as 4.2, 4.3, and 4.1 in any order;
    automatic numbering never replaces them.
    """
    m = re.match(r'^(?:рисунок|рис\.?)\s*(\d+(?:\.\d+)*)', (alt or '').strip(), flags=re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _explicit_table_number(title: str) -> Optional[str]:
    """Extract a table number from its caption prefix, preserving it verbatim."""
    m = re.match(r'^(?:таблица|табл\.?)\s*(\d+(?:\.\d+)*)', (title or '').strip(), flags=re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _is_figure_caption_text(s: str) -> bool:
    """Detect explicit figure captions, including optional emphasis wrappers.

    Require a separator (: – — -) or end of line after the number.
    Ordinary sentences beginning with a figure reference are not captions.
    """
    s = s.strip()
    return bool(re.match(
        r'^(?:\*{1,2}|_{1,2})?\s*(?:рисунок|рис\.?)\s*\d+(?:\.\d+)*(?:\s*[:–—-]\s*\S.*|\s*)$',
        s,
        flags=re.IGNORECASE
    ))


def _extract_figure_title_and_number(s: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract the figure title and number from a caption line.

    Return numbers verbatim without collapsing compound numbering.
    """
    s = s.strip()
    m = re.match(
        r'^(?:\*{1,2}|_{1,2})?\s*(?:рисунок|рис\.?)\s*(\d+(?:\.\d+)*)?(?:\s*[:–—-]\s*(.*?)|)$',
        s,
        flags=re.IGNORECASE
    )
    if not m:
        return None, None
    num_str = m.group(1)
    num = num_str if num_str else None
    raw_title = m.group(2) if m.group(2) else ""
    title = raw_title.strip().rstrip("*_").strip()
    return (title if title else None), num


def _is_generic_alt(alt: str) -> bool:
    """Detect empty, filename, or generic alt text eligible for caption replacement."""
    s = (alt or "").strip().lower()
    if not s:
        return True
    if s in ("image", "img", "рисунок", "рис", "рис.", "иллюстрация", "photo", "фото", "скриншот", "screenshot"):
        return True
    if re.search(r'\.(?:png|jpe?g|svg|webp|gif|bmp)$', s):
        return True
    if re.match(r'^(?:рисунок|рис\.?)?\s*\d+(?:\.\d+)*$', s):
        return True
    return False


def _remove_existing_tblW(tblPr) -> None:
    """Remove python-docx's w:tblW element to avoid duplicates on append."""
    for _old in tblPr.findall(qn('w:tblW')):
        tblPr.remove(_old)


def _lookup_image_layout(src: str, layouts: Dict[str, dict]) -> dict:
    basename = os.path.basename(unquote(src.strip("<>")))
    if basename in layouts:
        return layouts[basename]
    canonical = lambda name: re.sub(r"[\W_]+", "", name.casefold())
    matches = [layout for filename, layout in layouts.items()
               if canonical(os.path.basename(filename)) == canonical(basename)]
    return matches[0] if len(matches) == 1 else {}


def _emit_figure(doc, img_src: str, img_alt: str, images_dict, figure_number: "int | str", hide_captions: bool, layout: Optional[dict] = None):
    """Render a centered image with zero first-line indent and a figure caption."""
    layout = layout or {}
    figure_caption = clean_figure_caption(img_alt, figure_number)

    p_img = doc.add_paragraph()
    p_img.alignment = {
        "left": WD_ALIGN_PARAGRAPH.LEFT, "right": WD_ALIGN_PARAGRAPH.RIGHT,
    }.get(layout.get("align"), WD_ALIGN_PARAGRAPH.CENTER)
    p_img_pr = p_img._p.get_or_add_pPr()
    if layout.get("page_break_before"):
        p_img_pr.append(parse_xml(f'<w:pageBreakBefore {nsdecls("w")}/>'))
    p_img_pr.append(parse_xml(f'<w:keepLines {nsdecls("w")}/>'))
    if not hide_captions and layout.get("keep_caption_with_image", True):
        p_img_pr.append(parse_xml(f'<w:keepNext {nsdecls("w")}/>'))
    p_img_pr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="0" w:left="0" w:right="0"/>'))
    p_img_pr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="180" w:after="60" w:line="240" w:lineRule="auto"/>'))

    _insert_image_or_placeholder(doc, p_img, img_src, img_alt, images_dict, layout)

    if not hide_captions:
        p_fig_cap = doc.add_paragraph()
        p_fig_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_fig_cap_pr = p_fig_cap._p.get_or_add_pPr()
        p_fig_cap_pr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="0" w:left="0" w:right="0"/>'))
        p_fig_cap_pr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="60" w:after="240" w:line="240" w:lineRule="auto"/>'))

        run_fig = p_fig_cap.add_run(figure_caption)
        run_fig.font.name = "Times New Roman"
        run_fig.font.size = Pt(14)
        return p_fig_cap._p
    return p_img._p


def _emit_listing(doc, code_text: str, info: str, listing_number: int, hide_captions: bool) -> None:
    """Render a listing caption and a single-cell code table in the GOST style."""
    if not hide_captions:
        listing_title = clean_listing_caption(info, listing_number)
        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p_cap_pr = p_cap._p.get_or_add_pPr()
        p_cap_pr.append(parse_xml(f'<w:keepNext {nsdecls("w")}/>'))
        p_cap_pr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="0" w:left="0" w:right="0"/>'))
        p_cap_pr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="200" w:after="60" w:line="240" w:lineRule="auto"/>'))
        run_cap = p_cap.add_run(listing_title)
        run_cap.font.name = "Times New Roman"
        run_cap.font.size = Pt(12)
        run_cap.italic = True

    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl.autofit = False
    tblPr = tbl._tbl.tblPr
    tblPr.append(parse_xml(f'<w:tblInd {nsdecls("w")} w:w="0" w:type="dxa"/>'))
    _remove_existing_tblW(tblPr)
    tblPr.append(parse_xml(f'<w:tblW {nsdecls("w")} w:w="9355" w:type="dxa"/>'))
    tbl.columns[0].width = Mm(165)

    # Use the single project listing style: thin border and white background.
    set_listing_clean_borders(tbl, has_border=True)

    row = tbl.rows[0]
    cell = row.cells[0]
    # Keep the document background white, without gray shading.
    set_cell_background(cell, "FFFFFF")
    set_cell_margins(cell, top=80, bottom=80, left=140, right=140)

    code_lines = code_text.rstrip("\n").split("\n")
    p_code = cell.paragraphs[0]
    p_code.text = ""
    p_code.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_code_pr = p_code._p.get_or_add_pPr()
    p_code_pr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="0" w:left="0" w:right="0"/>'))
    p_code_pr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'))

    for l_idx, line in enumerate(code_lines):
        if l_idx > 0:
            p_code = cell.add_paragraph()
            p_code.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p_code_pr = p_code._p.get_or_add_pPr()
            p_code_pr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="0" w:left="0" w:right="0"/>'))
            p_code_pr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'))

        run_line = p_code.add_run(line if line else " ")
        # The project excludes monospace fonts, including in listings.
        run_line.font.name = "Times New Roman"
        run_line.font.size = Pt(10)
        # Use black text, without gray or colored highlighting.
        run_line.font.color.rgb = RGBColor(0, 0, 0)

def render_markdown_to_docx(
    doc: Document,
    markdown_text: str,
    images_dict: Optional[Dict[str, bytes]] = None,
    page_break_before_h1: bool = False,
    heading_alignment: str = "center",
    hide_captions: bool = False,
    latex_mode: str = "omml",
    image_layouts: Optional[Dict[str, dict]] = None
):
    """Render Markdown as formatted DOCX blocks.

    latex_mode selects native Word equations (omml) or deliberately simplified
    plain-text rendering without OMML (unicode).
    """
    if images_dict is None:
        images_dict = {}
    image_layouts = image_layouts or {}

    # Only explicit unicode mode uses simplified output; invalid modes use OMML.
    use_unicode_math = (latex_mode or "omml").strip().lower() == "unicode"

    # Normalize image paths containing spaces and parentheses.
    def _fix_img_target(m):
        alt = m.group(1)
        src = m.group(2).strip()
        if not (src.startswith('<') and src.endswith('>')) and ('(' in src or ')' in src or ' ' in src):
            return f'![{alt}](<{src}>)'
        return m.group(0)

    clean_md = re.sub(r'!\[([^\]]*)\]\((.+?\.(?:png|jpg|jpeg|gif|bmp|webp|tiff|svg))\)', _fix_img_target, markdown_text, flags=re.IGNORECASE)

    # Remove AI search-grounding markers from Gemini, ChatGPT, and Perplexity.
    clean_md = re.sub(r'\[cite:\s*[^\]]+\]', '', clean_md, flags=re.IGNORECASE)
    clean_md = re.sub(r'\[citation:\s*[^\]]+\]', '', clean_md, flags=re.IGNORECASE)
    clean_md = re.sub(r'【\d+(?::\d+)?†source】', '', clean_md)
    clean_md = re.sub(r'\[\^\d+\^\]', '', clean_md)
    clean_md = re.sub(r'[ \t]+([.,;:!?])', r'\1', clean_md)

    # Collapse single-line terminal command fences into inline code.
    clean_md = re.sub(r'(:\s*)\n+```(?:bash|sh|cmd|powershell|text)?\s*\n\s*([a-zA-Z0-9_\.\-\/\\~][^\n`]{0,80})\s*\n+```', r' `\2`.', clean_md, flags=re.IGNORECASE)

    # Unwrap text fences containing equations, lists, or base conversions.
    def _unwrap_text_block(m):
        inner = m.group(1).strip()
        has_math = bool(re.search(r'\$[^\$\n]+\$', inner))
        has_radix = bool(re.search(r'(?:\d+_{10}|[0-9a-fA-F]+_{16}|[01]+_2)\s*=', inner))
        has_binary_chain = bool(re.search(r'^[01]{8}(?:-[01]{8}){2,}', inner, re.MULTILINE))
        has_formula_list = bool(re.search(r'^[ \t]*[-–—]\s*(?:\$|[0-9a-fA-F]+_)', inner, re.MULTILINE))
        if has_math or has_radix or has_binary_chain or has_formula_list:
            return f"\n{inner}\n"
        return m.group(0)

    clean_md = re.sub(r'```(?:text|plain)?\s*\n([\s\S]*?)\n```', _unwrap_text_block, clean_md, flags=re.IGNORECASE)

    # Separate a colon-ended line from a following code literal to prevent
    # excessive spacing during justification.
    clean_md = re.sub(r'(:\s*)\n\s*(`[^`\n]+`)\s*$', r'\1\n\n\2\n', clean_md, flags=re.MULTILINE)
    clean_md = re.sub(r'(:\s*)\n\s*([0-9a-fA-F\-]{12,}|[01\-]{16,})\s*$', r'\1\n\n\2\n', clean_md, flags=re.MULTILINE)

    md = MarkdownIt("gfm-like", {"linkify": False})
    tokens = md.parse(clean_md)

    # Preserve author numbers verbatim, including compound numbers in any order.
    # used_* holds occupied number strings; *_counter supplies fallback numbers
    # only for captions without an author-supplied number.
    figure_counter = 0
    used_figure_numbers: set = set()
    table_counter = 0
    used_table_numbers: set = set()
    # Do not reuse a generated caption as a prefix for the next table,
    # or consecutive tables would consume each other's captions.
    auto_caption_el = None
    last_figure_caption_el = None
    listing_counter = 0
    h1_counter = 0
    last_heading_text = ""

    idx = 0
    n = len(tokens)

    while idx < n:
        tok = tokens[idx]

        # -------------------------------------------------------------
        # Headings.
        # -------------------------------------------------------------
        if tok.type == "heading_open":
            level = int(tok.tag[1])  # 1, 2, 3
            inline_tok = tokens[idx + 1] if idx + 1 < n else None
            # Flatten AST children so raw Markdown delimiters do not leak into DOCX.
            title_text = _inline_plain_text(inline_tok)
            clean_title = clean_heading_text(title_text)
            last_heading_text = clean_title

            # Empty headings must not produce orphaned empty paragraphs.

            # Skip empty headings entirely.
            if not clean_title:
                idx += 2
                while idx < n and tokens[idx].type != "heading_close":
                    idx += 1
                idx += 1
                continue

            p = doc.add_paragraph()
            pPr = p._p.get_or_add_pPr()

            # Optional H1 page breaks apply between sections, not before the first.
            if level == 1:
                if page_break_before_h1 and h1_counter > 0:
                    pPr.append(parse_xml(f'<w:pageBreakBefore {nsdecls("w")}/>'))
                h1_counter += 1

            # Keep headings with their text and together (GOST 7.32 section 6.2.3).
            pPr.append(parse_xml(f'<w:keepNext {nsdecls("w")}/>'))
            pPr.append(parse_xml(f'<w:keepLines {nsdecls("w")}/>'))
            # Disable heading hyphenation (GOST 7.32 section 6.2.3).
            pPr.append(parse_xml(f'<w:suppressAutoHyphens {nsdecls("w")}/>'))

            if level == 1:
                # H1 alignment: centered under GOST 7.32 or left under GOST 2.105.
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if heading_alignment == "center" else WD_ALIGN_PARAGRAPH.LEFT
                pPr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="0" w:left="0" w:right="0"/>'))
                pPr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="240" w:after="120" w:line="360" w:lineRule="auto"/>'))
                run = p.add_run(clean_title)
                run.font.name = "Times New Roman"
                run.font.size = Pt(14)
                run.bold = True
            elif level == 2:
                # H2: bold 14 pt, 1.25 cm indent, 12 pt before and 6 pt after.
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                pPr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="709"/>'))
                pPr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="240" w:after="120" w:line="360" w:lineRule="auto"/>'))
                run = p.add_run(clean_title)
                run.font.name = "Times New Roman"
                run.font.size = Pt(14)
                run.bold = True
            else:
                # Heading 3+
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                pPr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="709"/>'))
                pPr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="200" w:after="100" w:line="360" w:lineRule="auto"/>'))
                run = p.add_run(clean_title)
                run.font.name = "Times New Roman"
                run.font.size = Pt(13)
                run.bold = True

            idx += 2
            while idx < n and tokens[idx].type != "heading_close":
                idx += 1
            idx += 1
            continue

        # -------------------------------------------------------------
        # Fenced code listings.
        # -------------------------------------------------------------
        if tok.type in ("fence", "code_block"):
            code_text = tok.content
            # Empty fences must not produce blank listing tables.
            if not code_text.strip():
                idx += 1
                continue
            info = tok.info.strip() if tok.info else ""
            listing_counter += 1
            _emit_listing(doc, code_text, info, listing_counter, hide_captions)

            idx += 1
            continue

        # -------------------------------------------------------------
        # Images and figures.
        # -------------------------------------------------------------
        if tok.type == "paragraph_open":
            inline_tok = tokens[idx + 1] if idx + 1 < n else None
            if inline_tok and inline_tok.children and any(c.type == "image" for c in inline_tok.children):
                def _is_children_caption(children_list) -> Tuple[bool, Optional[str], Optional[int]]:
                    if any(c.type == "image" for c in children_list):
                        return False, None, None
                    meaningful = [
                        c for c in children_list
                        if not (
                            (c.type == "text" and not c.content.strip())
                            or c.type in ("softbreak", "hardbreak")
                        )
                    ]
                    if not meaningful:
                        return False, None, None
                    text = "".join(c.content for c in meaningful if c.type in ("text", "code_inline")).strip()
                    if len(text) <= 200 and _is_figure_caption_text(text):
                        t, num = _extract_figure_title_and_number(text)
                        return True, t, num
                    return False, None, None

                # Consume an explicit caption in the preceding document paragraph.
                preceding_caption_title: Optional[str] = None
                preceding_figure_num: Optional[str] = None
                if doc.paragraphs:
                    last_p = doc.paragraphs[-1]
                    last_text = last_p.text.strip()
                    user_caption = (
                        last_p._p is not last_figure_caption_el
                        and last_p._p is not auto_caption_el
                    )
                    if user_caption and len(last_text) <= 200 and _is_figure_caption_text(last_text):
                        preceding_caption_title, preceding_figure_num = _extract_figure_title_and_number(last_text)
                        p_elem = last_p._p
                        if p_elem.getparent() is not None:
                            p_elem.getparent().remove(p_elem)

                # Also inspect following token paragraphs for duplicate captions:
                # ![alt](src)
                #
                # Figure number, separator, and caption text.
                following_caption_title: Optional[str] = None
                following_figure_num: Optional[str] = None
                skip_following_paragraphs_tokens = 0

                peek_idx = idx + 3
                while peek_idx + 2 < n:
                    if (tokens[peek_idx].type == "paragraph_open" and
                        tokens[peek_idx + 1].type == "inline" and
                        tokens[peek_idx + 2].type == "paragraph_close"):
                        inline_cand = tokens[peek_idx + 1]
                        # A following paragraph with an image is another figure, not a caption.
                        if inline_cand.children and any(c.type == "image" for c in inline_cand.children):
                            break
                        cand_text = _inline_plain_text(inline_cand).strip()
                        if len(cand_text) <= 200 and _is_figure_caption_text(cand_text):
                            if not following_caption_title:
                                following_caption_title, following_figure_num = _extract_figure_title_and_number(cand_text)
                            skip_following_paragraphs_tokens += 3
                            peek_idx += 3
                            continue
                    break

                # Consume captions directly after an image within the same paragraph.
                consumed_children_indices: set = set()
                children = inline_tok.children
                for c_idx, c_tok in enumerate(children):
                    if c_tok.type == "image":
                        cand_sublist = []
                        k = c_idx + 1
                        while k < len(children) and children[k].type != "image":
                            cand_sublist.append(children[k])
                            k += 1
                        is_cap, cap_t, cap_n = _is_children_caption(cand_sublist)
                        if is_cap:
                            consumed_children_indices.update(range(c_idx + 1, k))
                            if not following_caption_title:
                                following_caption_title = cap_t
                            if following_figure_num is None:
                                following_figure_num = cap_n

                pending: list = []

                def _flush_text_segment() -> None:
                    if not pending:
                        return
                    is_cap, _, _ = _is_children_caption(pending)
                    if is_cap:
                        pending.clear()
                        return

                    meaningful = [
                        c for c in pending
                        if not (
                            (c.type == "text" and not c.content.strip())
                            or c.type in ("softbreak", "hardbreak")
                        )
                    ]
                    pending.clear()
                    if not meaningful:
                        return
                    p_t = doc.add_paragraph()
                    p_t.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    p_t_pr = p_t._p.get_or_add_pPr()
                    p_t_pr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="709"/>'))
                    p_t_pr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="0" w:after="0" w:line="360" w:lineRule="auto"/>'))
                    _render_inline_runs(p_t, meaningful, latex_mode)

                for c_idx, child in enumerate(children):
                    if c_idx in consumed_children_indices:
                        continue
                    if child.type == "image":
                        # Consume a pending caption preceding the image.
                        is_cap, cap_t, cap_n = _is_children_caption(pending)
                        if is_cap:
                            pending.clear()
                            if not preceding_caption_title:
                                preceding_caption_title = cap_t
                            if preceding_figure_num is None:
                                preceding_figure_num = cap_n
                        _flush_text_segment()

                        img_src = child.attrs.get("src", "") if child.attrs else ""
                        img_alt = child.content.strip()

                        cand_title = following_caption_title or preceding_caption_title
                        cand_num = following_figure_num if following_figure_num is not None else preceding_figure_num

                        if cand_title and (_is_generic_alt(img_alt) or not img_alt):
                            img_alt = cand_title

                        explicit = _explicit_figure_number(img_alt)
                        if explicit is None and cand_num is not None:
                            explicit = cand_num

                        if explicit is not None:
                            figure_number = explicit
                        else:
                            figure_counter += 1
                            while str(figure_counter) in used_figure_numbers:
                                figure_counter += 1
                            figure_number = str(figure_counter)
                        used_figure_numbers.add(str(figure_number))

                        last_figure_caption_el = _emit_figure(
                            doc, img_src, img_alt, images_dict, figure_number, hide_captions,
                            _lookup_image_layout(img_src, image_layouts)
                        )
                    else:
                        pending.append(child)

                _flush_text_segment()

                idx += 3 + skip_following_paragraphs_tokens
                continue

        # -------------------------------------------------------------
        # Markdown tables.
        # -------------------------------------------------------------
        if tok.type == "table_open":
            table_rows_data = []
            cur_row = []
            is_header = False
            col_alignments = []

            idx += 1
            while idx < n and tokens[idx].type != "table_close":
                t = tokens[idx]
                if t.type == "thead_open":
                    is_header = True
                elif t.type == "thead_close":
                    is_header = False
                elif t.type == "tr_open":
                    cur_row = []
                elif t.type == "tr_close":
                    table_rows_data.append((is_header, cur_row))
                elif t.type in ("th_open", "td_open"):
                    style = t.attrs.get("style", "") if t.attrs else ""
                    if "text-align:center" in style:
                        col_align = WD_ALIGN_PARAGRAPH.CENTER
                    elif "text-align:right" in style:
                        col_align = WD_ALIGN_PARAGRAPH.RIGHT
                    else:
                        col_align = WD_ALIGN_PARAGRAPH.LEFT

                    if len(col_alignments) <= len(cur_row):
                        col_alignments.append(col_align)
                    cur_cell = None
                elif t.type == "inline":
                    cur_cell = t
                elif t.type in ("th_close", "td_close"):
                    cur_row.append(cur_cell)
                idx += 1

            if table_rows_data:
                # Look for a caption in the preceding paragraph or subsection heading.
                # A caption prefix requires a number; ordinary prose stays intact.
                # Preserve manual numbers; otherwise assign the next free number.
                table_title = "Исходные данные и параметры"
                explicit_table_num: Optional[str] = None
                if doc.paragraphs:
                    last_p = doc.paragraphs[-1]
                    last_text = last_p.text.strip()
                    user_prefix = last_p._p is not auto_caption_el
                    m_tbl = re.match(r"^(?:таблица|табл\.?)\s*(\d+(?:\.\d+)*)(?:\s*([:–—-]|)\s*(.*)|\s*)$", last_text, flags=re.IGNORECASE)
                    if user_prefix and m_tbl and m_tbl.group(1):
                        sep = (m_tbl.group(2) or "").strip()
                        candidate = (m_tbl.group(3) or "").strip()
                        # Require a dash/colon separator or a number-only prefix.
                        # Do not consume ordinary sentences beginning with table references.
                        if sep or not candidate:
                            if candidate:
                                table_title = candidate
                            explicit_table_num = m_tbl.group(1)
                            p_elem = last_p._p
                            if p_elem.getparent() is not None:
                                p_elem.getparent().remove(p_elem)

                # Fall back to a subsection heading mentioning a table.
                if table_title == "Исходные данные и параметры" and last_heading_text:
                    if re.search(r"(?:таблица|табл\.?)", last_heading_text, flags=re.IGNORECASE):
                        candidate = re.sub(r"^(?:\d+\.?\s*)?(?:таблица|табл\.?)\s*(?:\d+)?\s*[:–—.\-]?\s*", "", last_heading_text, flags=re.IGNORECASE).strip()
                        if candidate:
                            table_title = candidate[0].upper() + candidate[1:]
                        if explicit_table_num is None:
                            explicit_table_num = _explicit_table_number(last_heading_text)

                if explicit_table_num is not None:
                    table_number = explicit_table_num
                else:
                    table_counter += 1
                    while str(table_counter) in used_table_numbers:
                        table_counter += 1
                    table_number = str(table_counter)
                used_table_numbers.add(str(table_number))
                tbl_caption_text = clean_table_caption(table_title, table_number)

                # GOST 7.32 section 6.8.2: caption above the table, left-aligned,
                # no first-line indent, number and title separated by a dash.
                if not hide_captions:
                    p_tbl_cap = doc.add_paragraph()
                    p_tbl_cap.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    p_tbl_cap_pr = p_tbl_cap._p.get_or_add_pPr()
                    p_tbl_cap_pr.append(parse_xml(f'<w:keepNext {nsdecls("w")}/>'))
                    p_tbl_cap_pr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="0" w:left="0" w:right="0"/>'))
                    p_tbl_cap_pr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="240" w:after="80" w:line="240" w:lineRule="auto"/>'))
                    run_tbl_cap = p_tbl_cap.add_run(tbl_caption_text)
                    run_tbl_cap.font.name = "Times New Roman"
                    run_tbl_cap.font.size = Pt(14)
                    auto_caption_el = p_tbl_cap._p

                # Align the full-width Word table with its left-aligned caption.
                cols_count = max([len(r[1]) for r in table_rows_data] or [1])
                cols_count = max(1, cols_count)
                tbl = doc.add_table(rows=max(1, len(table_rows_data)), cols=cols_count)
                tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
                tbl.autofit = True
                tblPr = tbl._tbl.tblPr
                tblPr.append(parse_xml(f'<w:tblInd {nsdecls("w")} w:w="0" w:type="dxa"/>'))
                _remove_existing_tblW(tblPr)
                tblPr.append(parse_xml(f'<w:tblW {nsdecls("w")} w:w="9355" w:type="dxa"/>'))
                set_table_gost_borders(tbl)

                for r_i, (is_hdr, row_cells) in enumerate(table_rows_data):
                    w_row = tbl.rows[r_i]
                    # Prevent row splitting (GOST 7.32 section 6.5.5, GOST 2.105-2019).
                    set_table_row_cant_split(w_row)
                    if is_hdr:
                        set_table_header_row(w_row)

                    for c_i, cell in enumerate(row_cells):
                        if c_i >= len(w_row.cells):
                            break
                        w_cell = w_row.cells[c_i]
                        set_cell_margins(w_cell, top=100, bottom=100, left=140, right=140)

                        p_c = w_cell.paragraphs[0]
                        p_c.text = ""

                        # Center headers; use Markdown alignment or defaults for data.
                        cell_alignment = WD_ALIGN_PARAGRAPH.CENTER if is_hdr else (
                            col_alignments[c_i] if c_i < len(col_alignments) else WD_ALIGN_PARAGRAPH.LEFT
                        )
                        p_c.alignment = cell_alignment
                        p_c_pr = p_c._p.get_or_add_pPr()
                        p_c_pr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="0" w:left="0" w:right="0"/>'))
                        p_c_pr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="20" w:after="20" w:line="240" w:lineRule="auto"/>'))

                        if cell:
                            _render_inline_runs(p_c, cell.children or [], latex_mode,
                                                base_bold=is_hdr, base_font_size=Pt(11 if is_hdr else 11.5))

            idx += 1
            continue

        # -------------------------------------------------------------
        # Ordinary paragraphs and display equations.
        # -------------------------------------------------------------
        if tok.type == "paragraph_open":
            inline_tok = tokens[idx + 1] if idx + 1 < n else None
            p_raw = inline_tok.content.strip() if inline_tok else ""

            # Detect display equations with optional external numbering.
            is_math_block = (p_raw.startswith("$$") and p_raw.endswith("$$") and len(p_raw) > 4) or bool(re.match(r'^\$\$(.*?)\$\$\s*(\((?:\d+(?:\.\d+)*|[а-яёА-ЯЁa-zA-Z0-9\.\-]+)\))$', p_raw, flags=re.DOTALL))
            if is_math_block:
                math_body, eq_num = _extract_equation_and_number(p_raw)

                if eq_num:
                    # GOST 7.32 section 6.7.3: center the equation and right-align its number.
                    # Use a borderless three-column table with widths 1200/6955/1200 dxa.
                    tbl = doc.add_table(rows=1, cols=3)
                    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
                    tblPr = tbl._tbl.tblPr
                    _remove_existing_tblW(tblPr)
                    tblPr.append(parse_xml(f'<w:tblW {nsdecls("w")} w:w="9355" w:type="dxa"/>'))
                    set_table_row_cant_split(tbl.rows[0])

                    row = tbl.rows[0]
                    c_left, c_center, c_right = row.cells[0], row.cells[1], row.cells[2]

                    for c, w_val in [(c_left, "1200"), (c_center, "6955"), (c_right, "1200")]:
                        set_cell_no_borders(c)
                        set_cell_margins(c, top=60, bottom=60, left=0, right=0)
                        tcPr = c._tc.get_or_add_tcPr()
                        for _old in tcPr.findall(qn('w:tcW')):
                            tcPr.remove(_old)
                        tcPr.append(parse_xml(f'<w:tcW {nsdecls("w")} w:w="{w_val}" w:type="dxa"/>'))

                    # Center the equation in the middle cell.
                    p_eq = c_center.paragraphs[0]
                    p_eq.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p_eq_pr = p_eq._p.get_or_add_pPr()
                    p_eq_pr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="0" w:left="0" w:right="0"/>'))
                    p_eq_pr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="60" w:after="60" w:line="240" w:lineRule="auto"/>'))

                    # Insert oMath, not oMathPara: the latter is invalid inside w:p.
                    # Unicode mode bypasses conversion and inserts plain text.
                    omml_elem = None if use_unicode_math else latex_to_omml(math_body, is_block=False)
                    if omml_elem is not None:
                        p_eq._p.append(omml_elem)
                    else:
                        r_math = p_eq.add_run(fallback_latex_to_unicode(math_body))
                        r_math.font.name = "Times New Roman"
                        r_math.font.size = Pt(13)
                        r_math.italic = True
                        r_math.font.color.rgb = RGBColor(0, 0, 0)

                    # Align the equation number with the right page margin.
                    p_num = c_right.paragraphs[0]
                    p_num.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    p_num_pr = p_num._p.get_or_add_pPr()
                    p_num_pr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="0" w:left="0" w:right="0"/>'))
                    p_num_pr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="60" w:after="60" w:line="240" w:lineRule="auto"/>'))
                    r_num = p_num.add_run(eq_num)
                    r_num.font.name = "Times New Roman"
                    r_num.font.size = Pt(14)
                    r_num.font.color.rgb = RGBColor(0, 0, 0)

                else:
                    # Unnumbered equations use a centered paragraph.
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    pPr = p._p.get_or_add_pPr()
                    pPr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="0" w:left="0" w:right="0"/>'))
                    pPr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="140" w:after="140" w:line="240" w:lineRule="auto"/>'))
                    # As above, use oMath, not oMathPara; unicode mode uses text.
                    omml_elem = None if use_unicode_math else latex_to_omml(math_body, is_block=False)
                    if omml_elem is not None:
                        p._p.append(omml_elem)
                    else:
                        r_math = p.add_run(fallback_latex_to_unicode(math_body))
                        r_math.font.name = "Times New Roman"
                        r_math.font.size = Pt(13)
                        r_math.italic = True
                        r_math.font.color.rgb = RGBColor(0, 0, 0)

                idx += 2
                while idx < n and tokens[idx].type != "paragraph_close":
                    idx += 1
                idx += 1
                continue

            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            pPr = p._p.get_or_add_pPr()

            # GOST 7.32 / GOST 2.105: equation explanations have no first-line indent;
            # standalone code/data lines are centered with no first-line indent.
            # Prose uses 1.25 cm (709 dxa) indent, 1.5 spacing, and zero paragraph gaps.
            first_line = 709
            para_text = inline_tok.content.strip() if inline_tok else ""
            if para_text.lower().startswith(('где ', 'где:')):
                first_line = 0
            elif para_text.startswith('`') and para_text.endswith('`') and '\n' not in para_text:
                first_line = 0
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER

            pPr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="{first_line}"/>'))
            pPr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="0" w:after="0" w:line="360" w:lineRule="auto"/>'))

            if inline_tok and inline_tok.children:
                _render_inline_runs(p, inline_tok.children, latex_mode)
            elif inline_tok:
                _render_text_with_latex(p, inline_tok.content, latex_mode=latex_mode)

            idx += 2
            while idx < n and tokens[idx].type != "paragraph_close":
                idx += 1
            idx += 1
            continue

        # -------------------------------------------------------------
        # Nested bullet and ordered lists under GOST 7.32.
        # -------------------------------------------------------------
        if tok.type in ("bullet_list_open", "ordered_list_open"):
            list_stack = []
            cur_delim = getattr(tok, "markup", ".") or "."
            if cur_delim not in (".", ")"):
                cur_delim = "."
            list_stack.append({
                "type": tok.type,
                "is_ordered": (tok.type == "ordered_list_open"),
                "delim": cur_delim,
                # Honor markdown-it's start attribute for continued/interrupted lists
                # instead of restarting the author's numbering at one.
                "item_num": _list_start_number(tok)
            })
            idx += 1
            while idx < n and len(list_stack) > 0:
                cur_tok = tokens[idx]
                if cur_tok.type in ("bullet_list_open", "ordered_list_open"):
                    sub_delim = getattr(cur_tok, "markup", ".") or "."
                    if sub_delim not in (".", ")"):
                        sub_delim = "."
                    list_stack.append({
                        "type": cur_tok.type,
                        "is_ordered": (cur_tok.type == "ordered_list_open"),
                        "delim": sub_delim,
                        "item_num": _list_start_number(cur_tok)
                    })
                elif cur_tok.type in ("bullet_list_close", "ordered_list_close"):
                    if list_stack:
                        list_stack.pop()
                elif cur_tok.type == "list_item_open":
                    if list_stack and getattr(cur_tok, "markup", None) in (".", ")"):
                        list_stack[-1]["delim"] = cur_tok.markup
                elif cur_tok.type == "list_item_close":
                    # Increment on item close, not inline tokens, so multiple
                    # paragraphs in one item do not skip numbers.
                    if list_stack:
                        list_stack[-1]["item_num"] += 1
                elif cur_tok.type in ("fence", "code_block"):
                    # Render fenced listings inside list items rather than dropping them.
                    fence_text = cur_tok.content
                    if fence_text.strip():
                        listing_counter += 1
                        fence_info = cur_tok.info.strip() if cur_tok.info else ""
                        _emit_listing(doc, fence_text, fence_info, listing_counter, hide_captions)
                elif cur_tok.type == "inline":
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    pPr = p._p.get_or_add_pPr()
                    depth = max(0, len(list_stack) - 1)
                    left_ind = depth * 360
                    pPr.append(parse_xml(f'<w:ind {nsdecls("w")} w:firstLine="709" w:left="{left_ind}" w:right="0"/>'))
                    pPr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="0" w:after="0" w:line="360" w:lineRule="auto"/>'))

                    top_list = list_stack[-1] if list_stack else {"is_ordered": False, "delim": ".", "item_num": 1}
                    if top_list["is_ordered"]:
                        prefix = f"{top_list['item_num']}{top_list['delim']}\u00a0"
                    else:
                        prefix = "–\u00a0"

                    r_pre = p.add_run(prefix)
                    r_pre.font.name = "Times New Roman"
                    r_pre.font.size = Pt(14)
                    r_pre.font.color.rgb = RGBColor(0, 0, 0)

                    item_kids = cur_tok.children if cur_tok.children else []
                    # Move list-item images into following figure blocks:
                    # _render_inline_runs does not render images.
                    _render_inline_runs(p, [c for c in item_kids if c.type != "image"], latex_mode)
                    for im in [c for c in item_kids if c.type == "image"]:
                        im_src = im.attrs.get("src", "") if im.attrs else ""
                        im_alt = im.content.strip()
                        explicit = _explicit_figure_number(im_alt)
                        if explicit is not None:
                            im_num = explicit
                        else:
                            figure_counter += 1
                            while str(figure_counter) in used_figure_numbers:
                                figure_counter += 1
                            im_num = str(figure_counter)
                        used_figure_numbers.add(str(im_num))
                        _emit_figure(doc, im_src, im_alt, images_dict, im_num, hide_captions,
                                     _lookup_image_layout(im_src, image_layouts))
                idx += 1
            continue

        idx += 1


def _render_text_with_latex(paragraph, text_content: str, is_bold: bool = False, is_italic: bool = False, base_font_size=Pt(14), latex_mode: str = "omml"):
    """Render a text fragment with inline LaTeX equations."""
    use_unicode_math = (latex_mode or "omml").strip().lower() == "unicode"
    math_pattern = re.compile(r'\$([^\$\n]+)\$')
    last_idx = 0
    matches = list(math_pattern.finditer(text_content))

    if not matches:
        clean_text = apply_typography_rules(text_content)
        r = paragraph.add_run(clean_text)
        r.font.name = "Times New Roman"
        r.font.size = base_font_size
        r.bold = is_bold
        r.italic = is_italic
        r.font.color.rgb = RGBColor(0, 0, 0)
        return

    for match in matches:
        start, end = match.span()
        if start > last_idx:
            pre_text = text_content[last_idx:start]
            clean_text = apply_typography_rules(pre_text)
            r = paragraph.add_run(clean_text)
            r.font.name = "Times New Roman"
            r.font.size = base_font_size
            r.bold = is_bold
            r.italic = is_italic
            r.font.color.rgb = RGBColor(0, 0, 0)

        latex_expr = match.group(1).strip()
        omml_elem = None if use_unicode_math else latex_to_omml(latex_expr, is_block=False)
        if omml_elem is not None:
            paragraph._p.append(omml_elem)
        else:
            r_math = paragraph.add_run(fallback_latex_to_unicode(latex_expr))
            r_math.font.name = "Times New Roman"
            r_math.font.size = Pt(13)
            r_math.italic = True
            r_math.font.color.rgb = RGBColor(0, 0, 0)

        last_idx = end

    if last_idx < len(text_content):
        post_text = text_content[last_idx:]
        clean_text = apply_typography_rules(post_text)
        r = paragraph.add_run(clean_text)
        r.font.name = "Times New Roman"
        r.font.size = base_font_size
        r.bold = is_bold
        r.italic = is_italic
        r.font.color.rgb = RGBColor(0, 0, 0)


def _render_inline_runs(paragraph, children, latex_mode: str = "omml", base_bold: bool = False, base_font_size=Pt(14)):
    """Render bold, italic, inline code, and equation tokens."""
    bold_depth = 0
    italic_depth = 0

    for child in children:
        is_bold = base_bold or bold_depth > 0
        is_italic = italic_depth > 0
        if child.type == "strong_open":
            bold_depth += 1
        elif child.type == "strong_close":
            bold_depth -= 1
        elif child.type == "em_open":
            italic_depth += 1
        elif child.type == "em_close":
            italic_depth -= 1
        elif child.type == "code_inline":
            # Inline code shares the body's Times New Roman 14 pt font.
            # Nonbreaking hyphens keep MAC addresses and binary chains together.
            code_text = child.content
            code_text = re.sub(
                r'\b[0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5}\b',
                lambda m: m.group(0).replace('-', '\u2011'),
                code_text
            )
            code_text = re.sub(
                r'\b[01]{8}(?:-[01]{8})+\b',
                lambda m: m.group(0).replace('-', '\u2011'),
                code_text
            )
            run = paragraph.add_run(code_text)
            run.font.name = "Times New Roman"
            run.font.size = base_font_size
            # Use black equation text under GOST, not colored text.
            run.font.color.rgb = RGBColor(0, 0, 0)
            run.bold = is_bold
            run.italic = is_italic
        elif child.type == "text":
            _render_text_with_latex(paragraph, child.content, is_bold=is_bold, is_italic=is_italic,
                                    base_font_size=base_font_size, latex_mode=latex_mode)
        elif child.type in ("softbreak", "hardbreak"):
            # Treat hard breaks as spaces too, so adjacent words do not merge.
            run = paragraph.add_run(" ")
            run.font.name = "Times New Roman"
            run.font.size = base_font_size
            run.font.color.rgb = RGBColor(0, 0, 0)


def _find_image_bytes(src: str, images_dict: Dict[str, bytes]) -> Optional[bytes]:
    """Find image bytes in the supplied dictionary using normalized names."""
    if not images_dict:
        return None
    from urllib.parse import unquote

    candidates = [
        src,
        unquote(src),
        os.path.basename(src),
        unquote(os.path.basename(src)),
        src.strip(),
        os.path.basename(src).strip()
    ]
    for c in candidates:
        if c in images_dict:
            return images_dict[c]

    lower_dict = {k.lower().strip(): v for k, v in images_dict.items()}
    for c in candidates:
        if c.lower().strip() in lower_dict:
            return lower_dict[c.lower().strip()]

    def normalize_key(s: str) -> str:
        return re.sub(r'[\s_\-\(\)\.]', '', s).lower()

    norm_dict = {normalize_key(k): v for k, v in images_dict.items()}
    for c in candidates:
        nk = normalize_key(c)
        if nk in norm_dict:
            return norm_dict[nk]

    return None


def find_missing_images(markdown_text: str, images_dict: Dict[str, bytes]) -> list:
    """Find image references whose files are absent from images_dict.

    Ignore fenced code and external http/https/data/blob URLs. These missing
    attachments become DOCX placeholders and trigger a pre-download warning.
    """
    if not markdown_text:
        return []
    # Image syntax inside fenced code is a literal, not an attachment reference.
    chunks = re.split(r"(```[\s\S]*?```)", markdown_text)
    text_outside_code = "".join(c for c in chunks if not c.startswith("```"))
    missing: list = []
    seen: set = set()
    for m in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', text_outside_code):
        src = (m.group(2) or "").strip().strip("<>").strip()
        if not src or src in seen:
            continue
        seen.add(src)
        low = src.lower()
        if low.startswith(("http://", "https://", "data:", "blob:")):
            continue
        if _find_image_bytes(src, images_dict or {}) is None:
            missing.append(src)
    return missing


def _image_size(image_bytes: bytes):
    """Read pixel dimensions from PNG/JPEG/GIF/BMP headers without Pillow."""
    try:
        if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            import struct
            w, h = struct.unpack(">II", image_bytes[16:24])
            return (w, h)
        if image_bytes[:2] == b"\xff\xd8":
            import struct
            pos = 2
            while pos < len(image_bytes) - 8:
                if image_bytes[pos] != 0xFF:
                    pos += 1
                    continue
                marker = image_bytes[pos + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                    h, w = struct.unpack(">HH", image_bytes[pos + 5:pos + 9])
                    return (w, h)
                size = struct.unpack(">H", image_bytes[pos + 2:pos + 4])[0]
                if size < 2:
                    break
                pos += 2 + size
        if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
            import struct
            w, h = struct.unpack("<HH", image_bytes[6:10])
            return (w, h)
        if image_bytes[:2] == b"BM":
            import struct
            w, h = struct.unpack("<II", image_bytes[18:26])
            return (w, abs(h))
    except Exception:
        pass
    return None


def _insert_image_or_placeholder(doc, paragraph, src: str, alt: str, images_dict: Dict[str, bytes], layout: Optional[dict] = None):
    """Insert an image from the binary dictionary or render a placeholder."""
    layout = layout or {}
    basename = os.path.basename(src)
    image_bytes = _find_image_bytes(src, images_dict)

    inserted = False
    if image_bytes:
        import io
        try:
            run = paragraph.add_run()
            # Limit height to avoid pushing tall screenshots to the next page
            # and leaving large gaps; the A4 text area is 257 mm high.
            width_mm = 165.0 * layout["width_percent"] / 100 if "width_percent" in layout else 155.0
            height_limit = layout.get("max_height_mm", 200.0)
            height_mm = None
            dims = _image_size(image_bytes)
            if dims and dims[0] > 0 and dims[1] > 0:
                height_mm = width_mm * dims[1] / dims[0]
                if height_mm > height_limit:
                    height_mm = height_limit
                    width_mm = height_mm * dims[0] / dims[1]
            if height_mm:
                run.add_picture(io.BytesIO(image_bytes), width=Mm(width_mm), height=Mm(height_mm))
            else:
                run.add_picture(io.BytesIO(image_bytes), width=Mm(width_mm))
            inserted = True
        except Exception:
            inserted = False

    if not inserted:
        run = paragraph.add_run(f" [ Иллюстрация: {alt} ({basename}) ] ")
        run.font.name = "Times New Roman"
        run.font.size = Pt(12)
        run.font.italic = True
        run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
