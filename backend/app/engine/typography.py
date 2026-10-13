"""Normalize Russian typography and text formatting under GOST 7.32-2017."""

import re
from markdown_it import MarkdownIt
from markdown_it.rules_inline.backticks import backtick

NBSP = '\u00a0'
NB_HYPHEN = '\u2011'

def _capture_code_span(state, silent):
    start = state.pos
    count = len(state.tokens)
    matched = backtick(state, silent)
    if not silent and len(state.tokens) > count and state.tokens[-1].type == "code_inline":
        state.env["code_spans"].append((start, state.pos))
    return matched

_inline_markdown = MarkdownIt("commonmark")
_inline_markdown.inline.ruler.at("backticks", _capture_code_span)

def strip_trailing_dot(text: str) -> str:
    """Remove a single trailing period while preserving ellipses."""
    s = (text or '').strip()
    if s.endswith('.') and not s.endswith('..'):
        s = s[:-1].rstrip()
    return s

def apply_typography_rules(text: str) -> str:
    """Apply Russian typography rules under GOST 7.32-2017.

    Bind short prepositions/conjunctions, numbered references, and measurement
    units with nonbreaking spaces. Normalize word-separating dashes and paired
    quotation marks, and keep technical hyphenated terms together.
    """
    if not text:
        return text

    # Normalize word-separating dashes to NBSP plus em dash.
    # Preserve arithmetic minus signs between numbers.
    def _dash_repl(m: 're.Match') -> str:
        left, right = m.group(1), m.group(2)
        if left[-1:].isdigit() and right[:1].isdigit():
            return m.group(0)
        return f'{left}{NBSP}— {right}'

    text = re.sub(r'(\S)\s+[-–—]\s+(\S)', _dash_repl, text)

    # Bind short prepositions and conjunctions to the following word.
    text = re.sub(r'\b([вВ]|[нН]а|[сС]|[пП]о|[кК]|[уУ]|[оО]|[иИ]з|[зЗ]а|[оО]т|[иИ]|[аА]|[нН]о|[дД]о|[пП]од|[пП]ри|[бБ]ез|[сС]о|[кК]о|[вВ]о|[оО]б|[оО]бо|[дД]ля|[нН]ад|[пП]ро|[мМ]еж)\s+', rf'\g<1>{NBSP}', text)

    # Bind initials and surnames in either order.
    text = re.sub(r'\b([А-ЯЁ]\.\s*[А-ЯЁ]\.)\s+([А-ЯЁ][а-яё\-]+)', rf'\g<1>{NBSP}\g<2>', text)
    text = re.sub(r'\b([А-ЯЁ][а-яё\-]+)\s+([А-ЯЁ]\.\s*[А-ЯЁ]\.)', rf'\g<1>{NBSP}\g<2>', text)

    # Bind reference labels to their numbers.
    text = re.sub(r'(?i)\b(рисун(?:ок|ка|ку|ком|ке|ки|ках)|рис\.|таблиц(?:а|ы|е|у|ей|ам|ах)|табл\.|листинг(?:а|у|ом|е|и)?|вариант(?:а|у|ом|е)?|групп(?:а|ы|е|у|ой)?|стр\.|с\.)\s+(\d+)', rf'\g<1>{NBSP}\g<2>', text)
    # The numero sign is not a word character, so a word boundary cannot match it.
    text = re.sub(r'(?:(?<=\s)|^)(№)\s*(\d+)', rf'\g<1>{NBSP}\g<2>', text)

    # Bind numbers to measurement units and year suffixes.
    text = re.sub(r'(\d+)\s+(мм|см|м|км|мс|с|мин|ч|байт|КБ|МБ|ГБ|бит|кбит|Мбит|Гбит|Гц|кГц|МГц|ГГц|В|А|Вт|кВт|pt|dxa|г\.|года)(?!\w)', rf'\g<1>{NBSP}\g<2>', text)

    # Convert paired quotation marks to guillemets without changing
    # unpaired inch marks such as 15" or 2.5".
    text = re.sub(r'[“„]([^”„\n]+?)[”"]', r'«\1»', text)
    text = re.sub(r'(?<!\d)"([^"\n]+?)"', r'«\1»', text)

    # Nonbreaking hyphens (U+2011) keep MAC addresses together.
    text = re.sub(
        r'\b[0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5}\b',
        lambda m: m.group(0).replace('-', NB_HYPHEN),
        text
    )

    # Keep hyphen-separated binary octets together.
    text = re.sub(
        r'\b[01]{8}(?:-[01]{8})+\b',
        lambda m: m.group(0).replace('-', NB_HYPHEN),
        text
    )

    # Keep hyphenated technical terms and abbreviations together.
    text = re.sub(
        r'\b(MAC|IPv4|IPv6|IP|Wi|TCP|UDP|DHCP|DNS|USB|Web|LAN|VLAN)-([а-яёА-ЯЁa-zA-Z0-9]+)\b',
        lambda m: f'{m.group(1)}{NB_HYPHEN}{m.group(2)}',
        text
    )
    text = re.sub(r'\bWi-Fi\b', f'Wi{NB_HYPHEN}Fi', text)

    return text

def apply_typography_outside_code(text: str) -> str:
    """Preserve original code spans with delimiters of any length."""
    spans = []
    _inline_markdown.parseInline(text, {"code_spans": spans})
    parts = []
    offset = 0
    for start, end in sorted(spans):
        parts.append(apply_typography_rules(text[offset:start]))
        parts.append(text[start:end])
        offset = end
    parts.append(apply_typography_rules(text[offset:]))
    return "".join(parts)

def clean_heading_text(title: str) -> str:
    """Remove a heading's trailing period and apply GOST 7.32 typography."""
    clean = strip_trailing_dot(title)
    return apply_typography_rules(clean)

def clean_figure_caption(alt: str, figure_number: "int | str") -> str:
    """Format a GOST 7.32 figure caption using the supplied number verbatim.

    Compound author numbers are preserved; automatic numbering is a fallback.
    """
    clean = strip_trailing_dot(alt)
    # A number-only caption is also a prefix; strip it to avoid duplicate labels.
    clean = re.sub(r'^(рисунок|рис\.?)\s*\d+(?:\.\d+)*\s*[:–—.\-]?\s*', '', clean, flags=re.IGNORECASE)
    clean = apply_typography_rules(clean)
    if not clean:
        clean = "Иллюстрация"
    first_letter = re.search(r'[^\W\d_]', clean, flags=re.UNICODE)
    if first_letter:
        index = first_letter.start()
        clean = clean[:index] + clean[index].upper() + clean[index + 1:]
    return f"Рисунок{NBSP}{figure_number} — {clean}"

def clean_table_caption(title: str, table_number: "int | str") -> str:
    """Format a GOST 7.32 table caption, preserving compound numbers verbatim."""
    clean = strip_trailing_dot(title)
    clean = re.sub(r'^(таблица|табл\.?)\s*\d+(?:\.\d+)*\s*[:–—.\-]?\s*', '', clean, flags=re.IGNORECASE)
    clean = apply_typography_rules(clean)
    if not clean:
        clean = "Исходные данные и параметры"
    return f"Таблица{NBSP}{table_number} — {clean}"

def clean_listing_caption(info: str, listing_number: int) -> str:
    """Format a listing caption with an explicit title or source-code language."""
    info = info.strip()
    if ":" in info:
        _, filename = info.split(":", 1)
        clean_name = filename.strip()
        return f"Листинг{NBSP}{listing_number} — {clean_name}"

    title_match = re.search(r'title=["\'](.*?)["\']', info)
    if title_match:
        clean_name = title_match.group(1).strip()
        return f"Листинг{NBSP}{listing_number} — {clean_name}"

    paren_match = re.search(r'\((.*?)\)', info)
    if paren_match:
        clean_name = paren_match.group(1).strip()
        return f"Листинг{NBSP}{listing_number} — {clean_name}"

    lang = info.split()[0] if info else ""
    if lang:
        return f"Листинг{NBSP}{listing_number} — Исходный код ({lang})"
    return f"Листинг{NBSP}{listing_number} — Исходный код"
