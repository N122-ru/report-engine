"""Audit OpenXML documents for GOST 7.32 and GOST 2.105 compliance."""

import re
from typing import Dict, List
from docx import Document
from docx.oxml.ns import qn

from ..models.linter import LinterIssue, LinterMetrics, LinterResult

# The project requires Times New Roman under GOST 7.32. Cambria Math and
# Symbol are allowed only in equations, where Word selects them for OMML.
ALLOWED_FONTS = frozenset({"Times New Roman", "Cambria Math", "Symbol"})

def lint_docx_document(docx_file_or_stream) -> LinterResult:
    """Run a complete DOCX compliance audit."""
    doc = Document(docx_file_or_stream)

    errors: List[LinterIssue] = []
    warnings: List[LinterIssue] = []

    # Check page margins.
    sec = doc.sections[0]
    left_mm = round(sec.left_margin.mm, 1)
    right_mm = round(sec.right_margin.mm, 1)
    top_mm = round(sec.top_margin.mm, 1)
    bottom_mm = round(sec.bottom_margin.mm, 1)

    margins_mm = {
        "left": left_mm,
        "right": right_mm,
        "top": top_mm,
        "bottom": bottom_mm
    }

    if abs(left_mm - 30.0) > 2.0:
        errors.append(LinterIssue(
            type="MARGINS",
            severity="ERROR",
            message=f"Левое поле ({left_mm} мм) нарушает ГОСТ 7.32. Требуется 30 мм (±2 мм).",
            location="Параметры страницы",
            fix_suggestion="Установите левое поле равным 30 мм"
        ))

    if abs(right_mm - 15.0) > 2.0:
        errors.append(LinterIssue(
            type="MARGINS",
            severity="ERROR",
            message=f"Правое поле ({right_mm} мм) нарушает ГОСТ 7.32. Требуется 15 мм (±2 мм).",
            location="Параметры страницы",
            fix_suggestion="Установите правое поле равным 15 мм"
        ))

    if abs(top_mm - 20.0) > 2.0:
        errors.append(LinterIssue(
            type="MARGINS",
            severity="ERROR",
            message=f"Верхнее поле ({top_mm} мм) нарушает ГОСТ 7.32. Требуется 20 мм (±2 мм).",
            location="Параметры страницы",
            fix_suggestion="Установите верхнее поле равным 20 мм"
        ))

    if abs(bottom_mm - 20.0) > 2.0:
        errors.append(LinterIssue(
            type="MARGINS",
            severity="ERROR",
            message=f"Нижнее поле ({bottom_mm} мм) нарушает ГОСТ 7.32. Требуется 20 мм (±2 мм).",
            location="Параметры страницы",
            fix_suggestion="Установите нижнее поле равным 20 мм"
        ))

    # Check empty paragraphs, headings, and captions.
    figures_found = []
    tables_found = []
    listings_count = 0
    all_body_text = []
    reference_paragraphs = []
    heading_texts = []

    consecutive_empty = 0
    empty_paragraphs_count = 0

    for idx, p in enumerate(doc.paragraphs):
        text = p.text.strip()
        has_drawing = len(p._element.xpath('.//w:drawing')) > 0
        has_math = len(p._element.xpath('.//m:oMath | .//m:oMathPara')) > 0
        has_sect = len(p._element.xpath('.//w:sectPr')) > 0
        is_empty = (len(text) == 0 and not has_drawing and not has_math and not has_sect)

        if is_empty:
            empty_paragraphs_count += 1
            consecutive_empty += 1
        else:
            if consecutive_empty >= 3:
                errors.append(LinterIssue(
                    type="LAYOUT",
                    severity="ERROR",
                    message=f"Обнаружено {consecutive_empty} пустых абзацев подряд перед элементом «{text[:35]}...». По ГОСТ верстка пустыми строками запрещена.",
                    location=f"Параграф {idx - consecutive_empty} – {idx}",
                    fix_suggestion="Замените пустые строки на разрыв страницы (Ctrl+Enter) или интервалы абзаца"
                ))
            elif consecutive_empty == 2:
                warnings.append(LinterIssue(
                    type="LAYOUT",
                    severity="WARNING",
                    message=f"Обнаружено 2 пустых абзаца подряд. Избегайте вертикального выравнивания клавишей Enter.",
                    location=f"Параграф {idx - 2} – {idx}",
                    fix_suggestion="Используйте свойства абзаца (интервалы до/после)"
                ))
            consecutive_empty = 0

        if not is_empty:
            # Count bibliography text toward volume, but skip other checks:
            # numbered entries could otherwise be mistaken for headings.
            if p.style.name == "Bibliography":
                all_body_text.append(text)
                continue
            # Extract equation text for metrics and references when prose is absent.
            if not text and has_math:
                math_texts = p._element.xpath('.//m:t')
                extracted_math = " ".join(t.text for t in math_texts if t.text)
                if extracted_math:
                    text = extracted_math
            all_body_text.append(text)

            # Detect headings by direct Normal formatting (bold, keepNext,
            # keepLines), not Heading styles or the prose's first word.
            is_heading = p.style.name.startswith("Heading") or (
                bool(p._p.xpath('./w:pPr/w:keepNext'))
                and bool(p._p.xpath('./w:pPr/w:keepLines'))
                and bool(p.runs)
                and all(run.bold for run in p.runs if run.text.strip())
            )
            if is_heading:
                heading_texts.append(text)

            # Exclude signature hints and the city/year footer.
            is_meta = any(text.startswith(m) for m in ["(должность", "(подпись", "(дата", "(группа"]) or bool(re.match(r"^.+\s(19|20)\d{2}$", text))

            if is_heading and not is_meta:
                if text.endswith(".") and not text.endswith(".."):
                    errors.append(LinterIssue(
                        type="PUNCTUATION",
                        severity="ERROR",
                        message=f"Обнаружена точка в конце заголовка: «{text}». Точки в заголовках запрещены по ГОСТ 7.32.",
                        location=f"Параграф {idx + 1}",
                        fix_suggestion="Удалите завершающую точку в заголовке"
                    ))

            # Figure captions require a separator or end of line after the number.
            # Preserve author numbering verbatim, including compound numbers.
            fig_match = re.match(r"^(?:Рисунок|Рис\.)\s+(\d+(?:\.\d+)*)(?:\s*([–—\-:])\s*(.*)|\s*)$", text, flags=re.IGNORECASE)
            if fig_match:
                fig_num = fig_match.group(1)
                dash_char = fig_match.group(2) or ""
                caption_tail = (fig_match.group(3) or "").strip()
                figures_found.append(fig_num)
                previous = doc.paragraphs[idx - 1] if idx else None
                if previous is None or (
                    not previous._p.xpath('.//w:drawing')
                    and not previous.text.strip().startswith('[ Иллюстрация:')
                ):
                    warnings.append(LinterIssue(
                        type="IMAGES", severity="WARNING",
                        message=f"Подпись «Рисунок {fig_num}» не связана с изображением.",
                        location=f"Параграф {idx + 1}",
                        fix_suggestion="Поместите рисунок непосредственно перед подписью"
                    ))

                if dash_char == "-":
                    errors.append(LinterIssue(
                        type="PUNCTUATION",
                        severity="ERROR",
                        message=f"В подписи рисунка «{text[:45]}...» используется дефис (-) вместо тире (—).",
                        location=f"Параграф {idx + 1}",
                        fix_suggestion="Замените дефис на тире (—)"
                    ))

                if text.endswith(".") and not text.endswith(".."):
                    errors.append(LinterIssue(
                        type="PUNCTUATION",
                        severity="ERROR",
                        message=f"Обнаружена точка в конце подписи рисунка: «{text}».",
                        location=f"Параграф {idx + 1}",
                        fix_suggestion="Удалите завершающую точку"
                    ))

            # Table captions use the same separator and verbatim numbering rules.
            tbl_match = re.match(r"^Таблица\s+(\d+(?:\.\d+)*)(?:\s*([–—\-:])\s*(.*)|\s*)$", text, flags=re.IGNORECASE)
            if tbl_match:
                tbl_num = tbl_match.group(1)
                dash_char = tbl_match.group(2) or ""
                tables_found.append(tbl_num)

                if dash_char == "-":
                    errors.append(LinterIssue(
                        type="PUNCTUATION",
                        severity="ERROR",
                        message=f"В подписи таблицы «{text[:45]}...» используется дефис (-) вместо тире (—).",
                        location=f"Параграф {idx + 1}",
                        fix_suggestion="Замените дефис на тире (—)"
                    ))

                if text.endswith(".") and not text.endswith(".."):
                    errors.append(LinterIssue(
                        type="PUNCTUATION",
                        severity="ERROR",
                        message=f"Обнаружена точка в конце подписи таблицы: «{text}».",
                        location=f"Параграф {idx + 1}",
                        fix_suggestion="Удалите завершающую точку"
                    ))

            if text and not fig_match and not tbl_match and not is_heading:
                reference_paragraphs.append(text)

            # Listings.
            if text.startswith("Листинг"):
                listings_count += 1
                listing_dash = re.search(r"Листинг\s+\d+\s*([–—-])", text)
                if listing_dash and listing_dash.group(1) == "-":
                    errors.append(LinterIssue(
                        type="PUNCTUATION",
                        severity="ERROR",
                        message=f"В подписи листинга «{text[:45]}...» используется дефис (-) вместо тире (—).",
                        location=f"Параграф {idx + 1}",
                        fix_suggestion="Замените дефис на тире (—)"
                    ))
                if text.endswith(".") and not text.endswith(".."):
                    errors.append(LinterIssue(
                        type="PUNCTUATION",
                        severity="ERROR",
                        message=f"Обнаружена точка в конце названия листинга: «{text}».",
                        location=f"Параграф {idx + 1}",
                        fix_suggestion="Удалите точку"
                    ))

    # Check explicit rFonts throughout the body, including tables; ignore inheritance.
    # Emit one warning per font, not per run, to avoid exhausting the score.
    bad_fonts: Dict[str, int] = {}
    for rFonts in doc.element.xpath('.//w:rFonts'):
        for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
            val = rFonts.get(qn(f'w:{attr}'))
            if val and val not in ALLOWED_FONTS:
                bad_fonts[val] = bad_fonts.get(val, 0) + 1
    for font_name in sorted(bad_fonts):
        n = bad_fonts[font_name]
        frag_word = "фрагмент" if n % 10 == 1 and n % 100 != 11 else ("фрагмента" if 2 <= n % 10 <= 4 and n % 100 not in (12, 13, 14) else "фрагментов")
        warnings.append(LinterIssue(
            type="FONTS",
            severity="WARNING",
            message=f"Нерекомендованный шрифт «{font_name}» ({n} {frag_word}). По ГОСТ 7.32 весь документ — Times New Roman (формулы — штатные шрифты Word).",
            location="Шрифты документа",
            fix_suggestion="Замените шрифт на Times New Roman"
        ))

    # Centered images/captions require zero first-line indent (SPEC 3.4).
    # Check explicit formatting only, not inherited style properties.
    for idx, p in enumerate(doc.paragraphs):
        text = p.text.strip()
        has_drawing = len(p._element.xpath('.//w:drawing')) > 0
        is_caption = text.startswith(("Рисунок", "Рис.", "Таблица", "Табл.", "Листинг"))
        if not ((has_drawing and not text) or is_caption):
            continue
        jc = p._element.xpath('.//w:jc')
        centered = any(el.get(qn('w:val')) == 'center' for el in jc)
        if not centered:
            continue
        ind = p._element.xpath('.//w:ind')
        first_line = ind[0].get(qn('w:firstLine')) if ind else None
        if first_line is not None and first_line != "0":
            warnings.append(LinterIssue(
                type="LAYOUT",
                severity="WARNING",
                message=f"Абзацный отступ у центрированного элемента «{text[:40]}»: красная строка запрещена, требуется 0.",
                location=f"Параграф {idx + 1}",
                fix_suggestion="Обнулите отступ первой строки (1.25 см → 0)"
            ))

    # Cross-references to figures and tables.
    full_text_joined = " ".join(all_body_text).lower()

    # Count references in prose, not captions. Expand ranges such as 12–16
    # and 4.1–4.3 while preserving other numbers verbatim.
    figure_refs: set[str] = set()
    for match in re.finditer(
        r"(?:рисун(?:ок|ка|ку|ком|ке|ки|ках|ков|ками)|рис\.)\s+(\d+(?:\.\d+)*)(?:\s*[–—-]\s*(\d+(?:\.\d+)*))?",
        " ".join(reference_paragraphs).lower(),
    ):
        first, last = match.group(1), match.group(2)
        figure_refs.add(first)
        if last:
            start_parts, end_parts = first.split("."), last.split(".")
            if start_parts[:-1] == end_parts[:-1]:
                start, end = int(start_parts[-1]), int(end_parts[-1])
                if 0 <= end - start <= 100:
                    figure_refs.update(".".join(start_parts[:-1] + [str(n)]) for n in range(start, end + 1))

    for f_num in set(figures_found):
        if f_num not in figure_refs:
            warnings.append(LinterIssue(
                type="REFERENCE",
                severity="WARNING",
                message=f"В тексте работы отсутствует прямая ссылка на «Рисунок {f_num}». По ГОСТ 7.32 на все иллюстрации должны быть ссылки в тексте.",
                location=f"Рисунок {f_num}",
                fix_suggestion=f"Добавьте в текст фразу: «...как представлено на рисунке {f_num}»"
            ))

    for t_num in set(tables_found):
        num_esc = re.escape(str(t_num))
        pattern = rf"(таблиц(а|ы|е|у|ей|ам|ах)\s+{num_esc}\b|табл\.\s*{num_esc}\b)"
        matches = re.findall(pattern, full_text_joined)
        if len(matches) <= 1:
            warnings.append(LinterIssue(
                type="REFERENCE",
                severity="WARNING",
                message=f"В тексте работы отсутствует ссылка на «Таблицу {t_num}».",
                location=f"Таблица {t_num}",
                fix_suggestion=f"Добавьте в текст фразу: «...приведены в таблице {t_num}»"
            ))

    # Search for local paths and working directories in prose, not code.
    for idx, text in enumerate(reference_paragraphs):
        if re.search(
            r"/(?:home|Users)/[^\s]+|[A-Za-z]:\\Users\\[^\s]+|"
            r"(?:из|в)\s+(?:папк[иеу]|каталог[аеу])\s+(?:edits|draft|final|скрины)\b",
            text, flags=re.IGNORECASE,
        ):
            warnings.append(LinterIssue(
                type="INTERNAL_NOTES", severity="WARNING",
                message="В тексте отчёта обнаружен локальный путь или служебная папка.",
                location=f"Абзац основного текста {idx + 1}",
                fix_suggestion="Опишите результат без упоминания путей и служебных папок"
            ))

    # Missing attachments are represented by text placeholders in the DOCX.
    seen_placeholders: set = set()
    for t in all_body_text:
        for ph in re.finditer(r"\[\s*Иллюстрация:\s*(.*?)\s*\(([^)]+)\)\s*\]", t):
            fname = (ph.group(2) or "").strip()
            if not fname or fname in seen_placeholders:
                continue
            seen_placeholders.add(fname)
            warnings.append(LinterIssue(
                type="IMAGES",
                severity="WARNING",
                message=f"Изображение «{fname}» не прикреплено: в документ вставлен плейсхолдер вместо рисунка. Загрузите файл перед скачиванием.",
                location=f"Иллюстрация {fname}",
                fix_suggestion="Прикрепите файл изображения с таким именем и соберите документ заново"
            ))

    # Bibliographic references under GOST 7.32 section 6.13 / GOST R 7.0.5.
    sources_section_found = any(
        re.search(r"(?:список|перечень)\s+(?:использованных\s+|основных\s+)?(источников|литературы)", t, flags=re.IGNORECASE)
        for t in all_body_text
    )
    if sources_section_found:
        # Accept bracketed citations such as [1], [1, 2], and [1-3].
        bib_refs = re.findall(r"\[\s*\d+(?:[\s,\–\-]\s*\d+)*(?:\s*,\s*с\.\s*\d+)?\s*\]", full_text_joined)
        if not bib_refs:
            warnings.append(LinterIssue(
                type="REFERENCE",
                severity="WARNING",
                message="В отчете присутствует раздел «Список источников», однако в тексте отсутствуют ссылки на литературу в квадратных скобках (например, [1]). По ГОСТ 7.32 на все приведенные источники должны быть ссылки в тексте.",
                location="Список источников",
                fix_suggestion="Добавьте в текст работы ссылки на источники, например: «...в соответствии с методикой [1]»"
            ))

    # Require aim/procedure/conclusion only when at least one is present,
    # avoiding false warnings for coursework with a different chapter structure.
    required_sections = (("Цель", r"^цел(?:ь|и)(?:\s|:|$)"), ("Ход работы", r"^ход работы(?:\s|:|$)"), ("Вывод", r"^вывод(?:ы|ов)?(?:\s|:|$)"))
    found_sections = set()
    for t in heading_texts:
        low = re.sub(r"^\d+(\.\d+)*\s+", "", t.strip().lower())
        for label, pattern in required_sections:
            if re.match(pattern, low):
                found_sections.add(label)
    if found_sections:
        for label, _pattern in required_sections:
            if label not in found_sections:
                warnings.append(LinterIssue(
                    type="STRUCTURE",
                    severity="WARNING",
                    message=f"В отчете есть разделы ({', '.join(sorted(found_sections))}), но отсутствует обязательный раздел «{label}».",
                    location="Структура отчета",
                    fix_suggestion=f"Добавьте раздел «{label}» — без него отчет неполон"
                ))

    # Preserve manual caption numbers; duplicates are author errors,
    # not generator numbering errors.
    for dup_num in sorted({n for n in figures_found if figures_found.count(n) > 1}):
        warnings.append(LinterIssue(
            type="NUMBERING",
            severity="WARNING",
            message=f"Дублирующийся номер подписи: «Рисунок {dup_num}» встречается {figures_found.count(dup_num)} раза. Проверьте нумерацию иллюстраций.",
            location=f"Рисунок {dup_num}",
            fix_suggestion="Пронумеруйте иллюстрации по порядку без повторов"
        ))

    compound_groups: Dict[str, set[int]] = {}
    for number in figures_found:
        if "." in number:
            prefix, ordinal = number.rsplit(".", 1)
            compound_groups.setdefault(prefix, set()).add(int(ordinal))
    for prefix, ordinals in compound_groups.items():
        if len(ordinals) < 2 or max(ordinals) > 100:
            continue
        for missing in sorted(set(range(1, max(ordinals) + 1)) - ordinals):
            warnings.append(LinterIssue(
                type="NUMBERING", severity="WARNING",
                message=f"В группе рисунков пропущен номер «{prefix}.{missing}».",
                location=f"Рисунки {prefix}",
                fix_suggestion="Проверьте, не потерян ли рисунок, либо уточните нумерацию"
            ))

    for dup_num in sorted({n for n in tables_found if tables_found.count(n) > 1}):
        warnings.append(LinterIssue(
            type="NUMBERING",
            severity="WARNING",
            message=f"Дублирующийся номер подписи: «Таблица {dup_num}» встречается {tables_found.count(dup_num)} раза. Проверьте нумерацию таблиц.",
            location=f"Таблица {dup_num}",
            fix_suggestion="Пронумеруйте таблицы по порядку без повторов"
        ))

    # Metrics and final score.
    raw_score = 100 - (len(errors) * 15) - (len(warnings) * 4)
    final_score = max(0, min(100, raw_score))

    # Estimate pages: one title page, ~220 words/page, +0.4/figure, +0.3/table.
    # Keep constants aligned with DocumentPreview's linterStatus.
    WORDS_PER_PAGE = 220
    PAGES_PER_FIGURE = 0.4
    PAGES_PER_TABLE = 0.3
    total_words = sum(len(t.split()) for t in all_body_text)
    est_pages = max(1, 1 + round(total_words / WORDS_PER_PAGE + len(figures_found) * PAGES_PER_FIGURE + len(doc.tables) * PAGES_PER_TABLE))

    metrics = LinterMetrics(
        margins_mm=margins_mm,
        page_count_estimate=est_pages,
        figures_count=len(figures_found),
        tables_count=len(tables_found),
        listings_count=listings_count,
        empty_paragraphs_count=empty_paragraphs_count
    )

    return LinterResult(
        is_valid=(len(errors) == 0),
        status="invalid" if errors else ("needs_review" if warnings else "ready"),
        score=final_score,
        errors=errors,
        warnings=warnings,
        metrics=metrics
    )
