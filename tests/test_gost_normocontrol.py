import sys, os
sys.path.insert(0, os.path.abspath("backend"))

import re
import pytest
import docx
from docx.oxml.ns import qn
from app.models.report import ReportMetadata, StudentInfo, TeacherInfo
from app.engine.generator import build_docx_report
from app.engine.linter import lint_docx_document
from app.engine.typography import apply_typography_rules, clean_figure_caption, clean_table_caption

def test_typography_edge_cases():
    # 1. Quotes with inches
    text = 'Экран 15" и процессор "Core i7"'
    res = apply_typography_rules(text)
    assert '15"' in res
    assert '«Core i7»' in res

    # 2. Dot in figure caption
    cap = clean_figure_caption("Рисунок 1. Архитектурная схема", 1)
    assert cap == "Рисунок\u00A01 — Архитектурная схема"
    assert clean_figure_caption("информация с msinfo32", 1) == "Рисунок\u00A01 — Информация с\u00A0msinfo32"

    # 3. Dot in table caption
    tcap = clean_table_caption("Таблица 2. Исходные параметры", 2)
    assert tcap == "Таблица\u00A02 — Исходные параметры"

    # Bind prepositions in either case and year suffixes with nonbreaking spaces.
    res_prep = apply_typography_rules("В отчете и в таблице за 2026 г. указаны данные.")
    assert "В\u00A0отчете" in res_prep
    assert "в\u00A0таблице" in res_prep
    assert "2026\u00A0г." in res_prep

def test_docx_preserves_literal_markdown_and_quotes_in_text_and_table():
    from app.models.report import GenerateOptions

    literal = 'print(`"value"`) ** * \'word\' \\n'
    md = f'Текст ``{literal}`` и **жирный *курсив***.\\nБуквальный перенос.\n\n| Значение |\n| --- |\n| ``{literal}`` |\n'
    document = docx.Document(build_docx_report(ReportMetadata(), md, options=GenerateOptions(include_title_page=False)))
    paragraph = document.paragraphs[0]
    assert literal in paragraph.text
    assert r'\nБуквальный' in paragraph.text
    assert any(run.text == 'курсив' and run.bold and run.italic for run in paragraph.runs)
    assert document.tables[0].cell(1, 0).text == literal

def test_table_constructor_markdown_renders_as_a_word_table():
    from app.models.report import GenerateOptions

    md = (
        "Таблица 1 — Параметры системы\n\n"
        "| Параметр | Значение | Примечание |\n"
        "| :--- | :--- | :--- |\n"
        "| Интерфейс | eth0 | Основной адаптер |\n"
    )
    document = docx.Document(build_docx_report(
        ReportMetadata(), md, options=GenerateOptions(include_title_page=False)
    ))

    assert len(document.tables) == 1
    assert document.tables[0].cell(0, 0).text == "Параметр"
    assert document.tables[0].cell(1, 1).text == "eth0"
    assert "Таблица\u00a01 — Параметры системы" in [p.text for p in document.paragraphs]

def test_docx_escaped_asterisks_remain_literal_and_latex_is_not_markdown():
    from app.models.report import GenerateOptions

    md = r'Литералы \* и \*\*; формула $x_{a_b} + \frac{1}{2}$.'
    document = docx.Document(build_docx_report(ReportMetadata(), md, options=GenerateOptions(include_title_page=False, latex_mode="unicode")))
    text = document.paragraphs[0].text
    assert 'Литералы * и **;' in text.replace('\u00a0', ' ')
    assert 'xₐ_b + (1)/(2)' in text

@pytest.mark.parametrize("logo_mode", ["none", "default"])
def test_title_header_uses_regular_type_and_explicitly_resets_body_indentation(logo_mode):
    meta = ReportMetadata(
        logo_mode=logo_mode,
        university="Тестовый технический университет",
        institute="Институт информационных технологий",
        department="Кафедра информационных систем",
    )
    document = docx.Document(build_docx_report(meta, ""))
    for paragraph in document.paragraphs[:4]:
        assert paragraph.paragraph_format.first_line_indent == 0
        assert all(run.bold is False for run in paragraph.runs if run.text)
        assert all(run.font.size.pt == 12 for run in paragraph.runs if run.text)
    assert next(paragraph for paragraph in document.paragraphs if paragraph.text == "ОТЧЕТ").runs[0].bold is True

def test_corrupted_image_fallback():
    # A corrupt image must not abort document generation.
    meta = ReportMetadata()
    md = "# Раздел\n![Схема](bad_image.png)"
    images = {"bad_image.png": b"not a real image content, just random bytes"}
    bio = build_docx_report(meta, md, images_dict=images)
    doc = docx.Document(bio)
    assert any("Иллюстрация" in p.text for p in doc.paragraphs)

def test_gost_xml_properties():
    meta = ReportMetadata(
        logo_mode="default",
        institute="Институт автоматики и информационных технологий",
        department="Электронные системы и информационная безопасность",
        work_theme="Исследование методов стеганографии в сетевых протоколах",
        discipline="Информационная безопасность",
        students=[
            StudentInfo(fio="А.А. Алексеев", group="1-ИАИТ-101"),
            StudentInfo(fio="И.И. Иванов", group="1-ИАИТ-101"),
            StudentInfo(fio="П.П. Петров", group="1-ИАИТ-101"),
        ],
        teachers=[
            TeacherInfo(fio="С.С. Сергеев", role="ст. преп."),
            TeacherInfo(fio="В.В. Смирнов", role="доцент"),
        ]
    )

    md = """# Цель работы
Изучение методов сокрытия данных в заголовках TCP/IP.

## Исходные данные
| Параметр | Значение | Описание |
| :--- | :---: | ---: |
| Порт | 8080 | Слушающий веб-сервер |
| Размер MTU | 1500 байт | Максимальный размер пакета |

### Перечень задач
1. Провести захват трафика
2. Выполнить анализ поля Identification
3. Сформулировать выводы

- Первый критерий надежности
- Второй критерий надежности
"""

    buf = build_docx_report(meta, md)
    doc = docx.Document(buf)

    # Title header paragraphs reserve logo space with w:left="1276".
    paragraphs = doc.paragraphs
    for p in paragraphs[:4]:
        pPr = p._p.pPr
        ind = pPr.find(qn('w:ind'))
        assert ind is not None
        assert ind.get(qn('w:left')) == '1276'

    # Headings require keepLines, keepNext, and suppressAutoHyphens.
    headings = [p for p in paragraphs if p.text in ("Цель работы", "Исходные данные", "Перечень задач")]
    assert len(headings) >= 3
    for h in headings:
        pPr = h._p.pPr
        assert pPr.find(qn('w:keepNext')) is not None
        assert pPr.find(qn('w:keepLines')) is not None
        assert pPr.find(qn('w:suppressAutoHyphens')) is not None

    # Every table row requires cantSplit.
    for tbl in doc.tables:
        for row in tbl.rows:
            trPr = row._tr.trPr
            assert trPr is not None
            assert trPr.find(qn('w:cantSplit')) is not None

    # Lists use w:firstLine="709" without tab characters.
    list_paras = [p for p in paragraphs if any(p.text.startswith(f"{i}.") for i in range(1, 10)) or p.text.startswith("–")]
    assert len(list_paras) == 5
    for lp in list_paras:
        pPr = lp._p.pPr
        ind = pPr.find(qn('w:ind'))
        assert ind is not None
        assert ind.get(qn('w:firstLine')) == '709'
        assert "\t" not in lp.text

    # Body-section footers use Times New Roman 12 pt (sz="24").
    body_sec = doc.sections[1]
    footer_p = body_sec.footer.paragraphs[0]
    fld = footer_p._p.find(qn('w:fldSimple'))
    assert fld is not None
    rPr = fld.find(qn('w:r')).find(qn('w:rPr'))
    assert rPr is not None
    assert rPr.find(qn('w:sz')).get(qn('w:val')) == '24'

def test_heading_alignment_toggle():
    from app.models.report import GenerateOptions
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    meta = ReportMetadata(work_theme="Тест")
    md = "# Цель работы\nТекст."

    # Default heading alignment is centered under GOST 7.32-2017.
    buf_def = build_docx_report(meta, md)
    doc_def = docx.Document(buf_def)
    h_def = [p for p in doc_def.paragraphs if p.text == "Цель работы"][0]
    assert h_def.alignment == WD_ALIGN_PARAGRAPH.CENTER

    # Department guides may request left alignment.
    buf_left = build_docx_report(meta, md, options=GenerateOptions(heading_alignment="left"))
    doc_left = docx.Document(buf_left)
    h_left = [p for p in doc_left.paragraphs if p.text == "Цель работы"][0]
    assert h_left.alignment == WD_ALIGN_PARAGRAPH.LEFT

def test_page_numbering_options():
    from app.models.report import GenerateOptions
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn

    meta = ReportMetadata(work_theme="Тест нумерации")
    md = "# Введение\nТекст первой страницы."

    # Default GOST 7.32 page numbering is centered.
    buf_center = build_docx_report(meta, md, options=GenerateOptions(page_numbering="center"))
    doc_c = docx.Document(buf_center)
    footer_p_c = doc_c.sections[1].footer.paragraphs[0]
    assert footer_p_c.alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert footer_p_c._p.find(qn('w:fldSimple')) is not None

    # GOST 2.105 page numbering can be right-aligned.
    buf_right = build_docx_report(meta, md, options=GenerateOptions(page_numbering="right"))
    doc_r = docx.Document(buf_right)
    footer_p_r = doc_r.sections[1].footer.paragraphs[0]
    assert footer_p_r.alignment == WD_ALIGN_PARAGRAPH.RIGHT
    assert footer_p_r._p.find(qn('w:fldSimple')) is not None

    # The none mode omits page numbers.
    buf_none = build_docx_report(meta, md, options=GenerateOptions(page_numbering="none"))
    doc_n = docx.Document(buf_none)
    sec_footer_p = doc_n.sections[1].footer.paragraphs
    assert len(sec_footer_p) == 0 or sec_footer_p[0]._p.find(qn('w:fldSimple')) is None

def test_title_page_geometry_and_samara_position(tmp_path):
    import subprocess, re, shutil
    if shutil.which("soffice") is None:
        pytest.skip("требуется LibreOffice (soffice) и poppler-utils")
    t1 = [TeacherInfo(fio="П.П. Петров", role="ст. преп.")]
    s4 = [
        StudentInfo(fio="И.И. Иванов", group="1-ИАИТ-101"),
        StudentInfo(fio="А.А. Алексеев", group="1-ИАИТ-101"),
        StudentInfo(fio="Б.Б. Борисов", group="1-ИАИТ-102"),
        StudentInfo(fio="В.В. Васильев", group="1-ИАИТ-103")
    ]
    meta = ReportMetadata(
        logo_mode="default",
        institute="Институт автоматики и информационных технологий",
        department="Электронные системы и информационная безопасность",
        work_theme="Исследование методов фильтрации трафика в распределенных вычислительных сетях",
        teachers=t1,
        students=s4,
        city="Самара",
        year=2026
    )

    bio = build_docx_report(meta, "# Введение\nТестовый текст отчета")
    docx_file = tmp_path / "report_4s.docx"
    pdf_file = tmp_path / "report_4s.pdf"
    docx_file.write_bytes(bio.getvalue())

    subprocess.run([
        "soffice", "--headless", "--convert-to", "pdf",
        "--outdir", str(tmp_path), str(docx_file)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    info = subprocess.check_output(["pdfinfo", str(pdf_file)]).decode()
    pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    assert pages == 2, f"Expected exactly 2 pages (1 title + 1 body), got {pages}"

    out_p1 = subprocess.check_output(["pdftotext", "-bbox-layout", "-f", "1", "-l", "1", str(pdf_file), "-"]).decode()
    y2_samara = None
    for m in re.finditer(r'<block xMin=\"([0-9.]+)\" yMin=\"([0-9.]+)\" xMax=\"([0-9.]+)\" yMax=\"([0-9.]+)\">', out_p1):
        x1, y1, x2, y2 = map(float, m.groups())
        end_pos = out_p1.find("</block>", m.start())
        words = re.findall(r"<word[^>]*>([^<]+)</word>", out_p1[m.start():end_pos])
        text = " ".join(words)
        if "Самара" in text:
            y2_samara = y2

    assert y2_samara is not None, "'Самара' must be on page 1"
    assert 750.0 <= y2_samara <= 785.2, f"Samara yMax={y2_samara:.1f}pt is out of bottom range [750, 785.2]"

def test_no_title_page_option():
    from app.models.report import GenerateOptions
    meta = ReportMetadata()
    bio = build_docx_report(meta, "# Введение\nТекст без титульника", options=GenerateOptions(include_title_page=False))
    doc = docx.Document(bio)
    assert len(doc.sections) == 1
    assert "Введение" in doc.paragraphs[0].text

def test_metadata_formatting_fields_and_page_break_before_h1():
    # Formatting settings can be supplied through ReportMetadata without options.
    meta = ReportMetadata(
        heading_alignment="center",
        page_numbering="right",
        page_break_before_h1=True
    )
    md = "# Раздел первый\nТекст первого раздела.\n# Раздел второй\nТекст второго раздела."
    bio = build_docx_report(meta, md)
    doc = docx.Document(bio)

    body_sec = doc.sections[1]
    footer_p = body_sec.footer.paragraphs[0]
    # Right-align page numbers.
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    assert footer_p.alignment == WD_ALIGN_PARAGRAPH.RIGHT

    # Center section headings.
    h1_paras = [p for p in doc.paragraphs if p.text in ("Раздел первый", "Раздел второй")]
    assert len(h1_paras) == 2
    assert h1_paras[0].alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert h1_paras[1].alignment == WD_ALIGN_PARAGRAPH.CENTER

    # The first H1 must not have a preceding page break.
    assert h1_paras[0]._p.pPr.find(qn('w:pageBreakBefore')) is None
    # The second H1 requires w:pageBreakBefore.
    assert h1_paras[1]._p.pPr.find(qn('w:pageBreakBefore')) is not None


def test_list_items_formatting_no_tab_and_gost_indent():
    """Verify lists use no tabs, a 1.25 cm (709 dxa) indent, and a nonbreaking space."""
    from app.models.report import ReportMetadata
    meta = ReportMetadata()
    md = """# Задание
1. Произвести анализ конфигурации системы.
2. Настроить политики безопасности и правила фильтрации.
3. Проверить защищенность канала передачи данных."""
    bio = build_docx_report(meta, md)
    doc = docx.Document(bio)

    list_paras = [p for p in doc.paragraphs if "анализ конфигурации" in p.text or "политики безопасности" in p.text]
    assert len(list_paras) == 2

    for p in list_paras:
        # List items must not contain tabs.
        assert "\t" not in p.text, f"Параграф списка содержит \\t: {repr(p.text)}"
        # Bind the numbered marker to its text with NBSP.
        assert ".\u00a0" in p.text, f"Параграф списка должен использовать неразрывный пробел: {repr(p.text)}"
        # Use GOST indentation: w:firstLine="709", w:left="0".
        ind = p._p.pPr.find(qn('w:ind'))
        assert ind is not None
        assert ind.get(qn('w:firstLine')) == "709"
        assert ind.get(qn('w:left')) == "0"


def test_hide_captions_option():
    """Verify hide_captions omits figure and listing captions."""
    from app.models.report import ReportMetadata, GenerateOptions
    md = """# Тестирование
```python
x = 10
print(x)
```
![Схема топологии сети](network.png)
"""
    # Captions are enabled by default.
    bio_default = build_docx_report(ReportMetadata(hide_captions=False), md)
    doc_default = docx.Document(bio_default)
    text_default = " ".join(p.text for p in doc_default.paragraphs)
    assert "Листинг" in text_default
    assert "Рисунок" in text_default

    # Explicitly hide captions.
    bio_hidden = build_docx_report(ReportMetadata(hide_captions=True), md)
    doc_hidden = docx.Document(bio_hidden)
    text_hidden = " ".join(p.text for p in doc_hidden.paragraphs)
    assert "Листинг" not in text_hidden
    assert "Рисунок" not in text_hidden

    # Hiding captions must preserve the code table and image.
    code_tables = [t for t in doc_hidden.tables if any("print(x)" in c.text for r in t.rows for c in r.cells)]
    assert len(code_tables) == 1


def test_plural_teacher_and_student_labels():
    """Verify singular and plural teacher/student labels on title pages."""
    from app.models.report import ReportMetadata, TeacherInfo, StudentInfo

    # One signatory uses a singular label.
    meta_single = ReportMetadata(
        teachers=[TeacherInfo(fio="П.П. Петров", role="доцент")],
        students=[StudentInfo(fio="И.И. Иванов", group="1-ИАИТ-101")]
    )
    doc_single = docx.Document(build_docx_report(meta_single, ""))
    # The title-page signature table is the document's first table.
    sig_tbl_single = doc_single.tables[0]
    single_texts = [cell.text.strip() for row in sig_tbl_single.rows for cell in row.cells]
    assert "Преподаватель" in single_texts
    assert "Преподаватели" not in single_texts
    assert "Студент" in single_texts
    assert "Студенты" not in single_texts

    # Multiple signatories use plural labels under GOST.
    meta_multi = ReportMetadata(
        teachers=[
            TeacherInfo(fio="П.П. Петров", role="доцент"),
            TeacherInfo(fio="С.С. Сидоров", role="профессор")
        ],
        students=[
            StudentInfo(fio="И.И. Иванов", group="1-ИАИТ-101"),
            StudentInfo(fio="А.А. Смирнов", group="1-ИАИТ-101")
        ]
    )
    doc_multi = docx.Document(build_docx_report(meta_multi, ""))
    sig_tbl_multi = doc_multi.tables[0]
    multi_texts = [cell.text.strip() for row in sig_tbl_multi.rows for cell in row.cells]
    assert "Преподаватели" in multi_texts
    assert "Преподаватель" not in multi_texts
    assert "Студенты" in multi_texts
    assert "Студент" not in multi_texts


def test_table_with_empty_cells_alignment():
    """Verify empty table cells preserve column positions."""
    from app.models.report import ReportMetadata
    md = """# Таблицы
| Колонка 1 | Колонка 2 | Колонка 3 |
| :--- | :--- | :--- |
| | Данные 2 | Данные 3 |
| Значение 1 | | Значение 3 |
"""
    bio = build_docx_report(ReportMetadata(), md)
    doc = docx.Document(bio)

    # The data table follows the title-page signature table.
    data_tbl = doc.tables[1]
    assert len(data_tbl.rows) == 3
    # In row two, the first cell is empty and the second retains its data.
    assert data_tbl.rows[1].cells[0].text.strip() == ""
    assert data_tbl.rows[1].cells[1].text.strip() == "Данные 2"
    assert data_tbl.rows[1].cells[2].text.strip() == "Данные 3"

    # In row three, the second cell is empty.
    assert data_tbl.rows[2].cells[0].text.strip() == "Значение 1"
    assert data_tbl.rows[2].cells[1].text.strip() == ""
    assert data_tbl.rows[2].cells[2].text.strip() == "Значение 3"


def test_nested_lists_parsing():
    """Verify closing a nested list does not end its parent list."""
    from app.models.report import ReportMetadata
    md = """# Списки
1. Первый пункт
   - Вложенный подпункт А
   - Вложенный подпункт Б
2. Второй пункт
3. Третий пункт
"""
    bio = build_docx_report(ReportMetadata(), md)
    doc = docx.Document(bio)

    texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    assert any("1.\xa0Первый пункт" in t for t in texts)
    assert any("–\xa0Вложенный подпункт А" in t for t in texts)
    assert any("–\xa0Вложенный подпункт Б" in t for t in texts)
    assert any("2.\xa0Второй пункт" in t for t in texts)
    assert any("3.\xa0Третий пункт" in t for t in texts)


def test_title_only_has_exactly_one_section_and_one_page():
    """Verify title-page-only exports have no empty second page."""
    from app.models.report import ReportMetadata
    bio = build_docx_report(ReportMetadata(), "")
    doc = docx.Document(bio)
    # Require exactly one section.
    assert len(doc.sections) == 1
    # Keep the city/year footer on the first page.
    assert any(re.search(r"(19|20)\d{2}", p.text) for p in doc.paragraphs)


def test_typography_prepositions_and_initials():
    """Verify nonbreaking spacing for prepositions and initials."""
    from app.engine.typography import apply_typography_rules
    # Bind the preposition to its following word.
    res1 = apply_typography_rules("у студента и у преподавателя")
    assert "у\u00a0студента" in res1
    assert "у\u00a0преподавателя" in res1

    # Initials precede the surname.
    res2 = apply_typography_rules("проверил И.И. Иванов на занятии")
    assert "И.И.\u00a0Иванов" in res2

    # Also support surname-first input for typography.
    res3 = apply_typography_rules("отчет сдал Петров П.П. вовремя")
    assert "Петров\u00a0П.П." in res3


def test_title_page_hyphenated_surname():
    """Verify capitalization of a synthetic hyphenated surname."""
    from app.models.report import ReportMetadata, StudentInfo
    meta = ReportMetadata(
        students=[StudentInfo(fio="А.Б. Примеров-Тестов", group="ИВТ-101")]
    )
    bio = build_docx_report(meta, "")
    doc = docx.Document(bio)
    sig_tbl = doc.tables[0]
    all_cells = [c.text.strip() for r in sig_tbl.rows for c in r.cells]
    assert "А.Б. Примеров-Тестов" in all_cells


def test_latex_mode_unicode_degrades_to_text():
    """Verify unicode mode uses plain text; default and invalid modes use native OMML."""
    from app.models.report import ReportMetadata, GenerateOptions
    md = "Текст $E=mc^2$.\n\n$$x_{ij} + \\sum_{k} a_k$$"

    def _xml(doc):
        return "\n".join(p._p.xml for p in doc.paragraphs)

    # Select the mode through metadata.
    doc_uni = docx.Document(build_docx_report(ReportMetadata(latex_mode="unicode"), md))
    assert "oMath" not in _xml(doc_uni)
    full_uni = " ".join(p.text for p in doc_uni.paragraphs)
    assert "E=mc" in full_uni and "∑" in full_uni

    # Explicit generation options also select the mode.
    doc_opt = docx.Document(build_docx_report(ReportMetadata(), md, options=GenerateOptions(latex_mode="unicode")))
    assert "oMath" not in _xml(doc_opt)

    # Default and invalid modes normalize to native OMML.
    for m in ("omml", "junk"):
        doc_d = docx.Document(build_docx_report(ReportMetadata(), md, options=GenerateOptions(latex_mode=m)))
        assert "oMath" in _xml(doc_d)


def test_linter_flags_non_gost_fonts():
    """Verify font warnings for external documents and clean generated output."""
    import io
    from app.engine.linter import lint_docx_document

    # Generated output uses Times New Roman and standard OMML fonts only.
    md = "# Цель\n\nТекст.\n\n```python\nx = 1\n```\n\n$$E=mc^2$$"
    res_own = lint_docx_document(build_docx_report(ReportMetadata(), md))
    assert not [w for w in res_own.warnings if w.type == "FONTS"]

    # Audit an external document using Calibri and Courier New.
    doc = docx.Document()
    r = doc.add_paragraph("Текст").add_run(" продолжение")
    r.font.name = "Calibri"
    r2 = doc.add_paragraph("Код").add_run("x=1")
    r2.font.name = "Courier New"
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    res_ext = lint_docx_document(buf)
    font_warns = [w for w in res_ext.warnings if w.type == "FONTS"]
    assert len(font_warns) == 2
    assert all(w.severity == "WARNING" for w in font_warns)
    assert any("Calibri" in w.message for w in font_warns)
    assert any("Courier New" in w.message for w in font_warns)


def test_math_symbols_cover_common_operators():
    """Verify the equation fallback preserves common operators."""
    from app.engine.math_utils import MATH_SYMBOLS, fallback_latex_to_unicode
    for cmd in (r'\sum', r'\prod', r'\int', r'\log', r'\ln', r'\lim',
                r'\sin', r'\cos', r'\leq', r'\geq', r'\neq', r'\times',
                r'\to', r'\rightarrow', r'\in', r'\notin'):
        assert cmd in MATH_SYMBOLS, cmd
    out = fallback_latex_to_unicode(r'\sum_{i=1}^n x_i + \int_0^1 \log x')
    assert '\\' not in out
    assert '∑' in out and '∫' in out and 'log x' in out


def test_table_caption_consumes_only_numbered_prefix():
    """Verify only explicit table captions are consumed, not ordinary sentences."""
    md_num = "Таблица 1 – Параметры сети\n\n| Узел | IP |\n|---|---|\n| srv | 1.1.1.1 |"
    doc = docx.Document(build_docx_report(ReportMetadata(), md_num))
    paras = [p.text for p in doc.paragraphs]
    assert not any("Таблица 1 – Параметры" in t for t in paras)
    assert any(t.startswith("Таблица 1 — Параметры") for t in paras)

    md_sent = "Таблица: данные отсутствуют\n\n| Узел | IP |\n|---|---|\n| srv | 1.1.1.1 |"
    doc2 = docx.Document(build_docx_report(ReportMetadata(), md_sent))
    paras2 = [p.text for p in doc2.paragraphs]
    assert any("Таблица: данные отсутствуют" in t for t in paras2)


def test_ordered_list_start_preserved():
    """Verify continuous numbering and author start values in interrupted lists."""
    import re

    def _nums(md):
        doc = docx.Document(build_docx_report(ReportMetadata(), md))
        return [re.match(r"^(\d+[.)])", p.text).group(1)
                for p in doc.paragraphs if re.match(r"^\d+[.)]", p.text)]

    # One continuous list numbers items 1,2,3, ignoring individual source markers.
    assert _nums("1. Раз\n\n2. Два\n\n5. Пять") == ["1.", "2.", "3."]
    # Interrupted lists preserve their start values: 1,2,3,5,6.
    md_broken = "1. Раз\n\nТекст между.\n\n2. Два\n\n```python\nx=1\n```\n\n5. Пять"
    assert _nums(md_broken) == ["1.", "2.", "5."]


def test_hybrid_caption_numbering():
    """Verify author numbers are preserved and fallback numbers avoid collisions."""
    md = "![Рисунок 5 — Схема](a.png)\n\n![Просто схема](b.png)\n\n![Рис. 2 — План](c.png)\n\n![Ещё](d.png)"
    doc = docx.Document(build_docx_report(ReportMetadata(), md))
    caps = [p.text for p in doc.paragraphs if p.text.startswith("Рисунок")]
    assert caps == ["Рисунок 5 — Схема", "Рисунок 1 — Просто схема", "Рисунок 2 — План", "Рисунок 3 — Ещё"]

    md_tbl = "Таблица 7 – Параметры\n\n| A |\n|---|\n| 1 |\n\n| B |\n|---|\n| 2 |"
    doc = docx.Document(build_docx_report(ReportMetadata(), md_tbl))
    caps = [p.text for p in doc.paragraphs if p.text.startswith("Таблица")]
    assert len(caps) == 2
    assert caps[0].startswith("Таблица 7 — Параметры")
    assert caps[1].startswith("Таблица 1 — Исходные данные")


def test_linter_duplicate_numbers():
    """Verify duplicate caption numbers produce NUMBERING warnings."""
    import io
    from app.engine.linter import lint_docx_document
    doc = docx.Document()
    doc.add_paragraph("Рисунок 1 — Схема")
    doc.add_paragraph("Рисунок 1 — План")
    doc.add_paragraph("Таблица 2 — Данные")
    doc.add_paragraph("Таблица 2 — Ещё")
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    res = lint_docx_document(buf)
    numbering = [w for w in res.warnings if w.type == "NUMBERING"]
    assert len(numbering) == 2


def test_multiline_math_with_outside_number():
    """Verify multiline display equations use OMML and right-aligned external numbers."""
    md = """# Расчетные формулы

Формула (1) определяет целевую функцию:

$$
f(x) = x^2 + 2x + 1
$$ (1)

Формула (2) определяет второе соотношение:

$$
E = mc^2
$$ (2)
"""
    buf = build_docx_report(ReportMetadata(), md)
    doc = docx.Document(buf)
    xml_str = doc._element.xml
    assert "oMath" in xml_str
    # Raw math delimiters must not remain in document text.
    plain_texts = [p.text for p in doc.paragraphs]
    assert not any("$$" in t for t in plain_texts)


def test_linter_omml_not_flagged_as_empty_lines():
    """Verify consecutive equations do not trigger false empty-paragraph warnings."""
    from app.engine.linter import lint_docx_document
    md = r"""# Формулы

В соответствии с формулой (1) и формулой (2):

$$
y_1 = a \cdot x_1 + b
$$ (1)

$$
y_2 = a \cdot x_2 + b
$$ (2)

$$
y_3 = a \cdot x_3 + b
$$ (3)

Завершающий текст раздела с описанием результатов.
"""
    buf = build_docx_report(ReportMetadata(), md)
    res = lint_docx_document(buf)
    empty_lines_warns = [w for w in res.warnings if w.type == "EMPTY_LINES"]
    assert len(empty_lines_warns) == 0
    assert res.score >= 90


def test_figure_duplicate_caption_absorption():
    """Verify duplicate user or AI figure captions are consumed."""
    # A caption can follow on the next line of the same paragraph.
    md1 = "# Раздел\n\n![Схема сети](net.png)\nРисунок 1 — Схема сети\n\nТекст после рисунка."
    doc1 = docx.Document(build_docx_report(ReportMetadata(), md1))
    p_texts1 = [p.text.strip() for p in doc1.paragraphs if p.text.strip()]
    caps1 = [t for t in p_texts1 if t.startswith("Рисунок")]
    assert len(caps1) == 1
    assert caps1[0] == "Рисунок 1 — Схема сети"
    assert p_texts1.count("Рисунок 1 — Схема сети") == 1
    assert "Текст после рисунка." in p_texts1

    # A caption can occupy a separate paragraph after the image.
    md2 = "# Раздел\n\n![Схема алгоритма](alg.png)\n\nРисунок 1 — Схема алгоритма\n\nТекст далее."
    doc2 = docx.Document(build_docx_report(ReportMetadata(), md2))
    p_texts2 = [p.text.strip() for p in doc2.paragraphs if p.text.strip()]
    caps2 = [t for t in p_texts2 if t.startswith("Рисунок")]
    assert len(caps2) == 1
    assert caps2[0] == "Рисунок 1 — Схема алгоритма"

    # Replace generic filename alt text with the meaningful caption below.
    md3 = "# Раздел\n\n![screen_01.png](screen_01.png)\nРисунок 2 — Настройка сетевого адаптера\n\nТекст."
    doc3 = docx.Document(build_docx_report(ReportMetadata(), md3))
    p_texts3 = [p.text.strip() for p in doc3.paragraphs if p.text.strip()]
    caps3 = [t for t in p_texts3 if t.startswith("Рисунок")]
    assert len(caps3) == 1
    assert caps3[0] == "Рисунок 2 — Настройка сетевого адаптера"

    # A caption can precede the image.
    md4 = "# Раздел\n\nРисунок 1 — Топология сети\n\n![Топология сети](top.png)\n\nТекст."
    doc4 = docx.Document(build_docx_report(ReportMetadata(), md4))
    p_texts4 = [p.text.strip() for p in doc4.paragraphs if p.text.strip()]
    caps4 = [t for t in p_texts4 if t.startswith("Рисунок")]
    assert len(caps4) == 1
    assert caps4[0] == "Рисунок 1 — Топология сети"

    # Consecutive images can each have duplicate captions.
    md5 = "# Раздел\n\n![Схема 1](a.png)\nРисунок 1 — Схема 1\n\n![Схема 2](b.png)\nРисунок 2 — Схема 2"
    doc5 = docx.Document(build_docx_report(ReportMetadata(), md5))
    p_texts5 = [p.text.strip() for p in doc5.paragraphs if p.text.strip()]
    caps5 = [t for t in p_texts5 if t.startswith("Рисунок")]
    assert len(caps5) == 2
    assert caps5[0] == "Рисунок 1 — Схема 1"
    assert caps5[1] == "Рисунок 2 — Схема 2"


def test_mac_and_binary_non_breaking_hyphens():
    """Verify U+2011 nonbreaking hyphens in MAC addresses and binary chains."""
    md = (
        "# Раздел\n\n"
        "MAC-адрес адаптера: `50-BB-B5-50-31-32` и в обычном тексте 50-BB-B5-50-31-32.\n\n"
        "Полное двоичное представление MAC-адреса:\n"
        "`01010000-10111011-10110101-01010000-00110001-00110010`\n"
    )
    doc = docx.Document(build_docx_report(ReportMetadata(), md))
    full_text = "\n".join(p.text for p in doc.paragraphs)

    # Prose uses U+2011 nonbreaking hyphens.
    assert "50\u2011BB\u2011B5\u201150\u201131\u201132" in full_text
    assert "MAC\u2011адрес" in full_text

    # Inline code also uses nonbreaking hyphens.
    assert "01010000\u201110111011\u201110110101\u201101010000\u201100110001\u201100110010" in full_text

    # Separate colon-ended prose and code literals to avoid justification gaps.
    p_texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    assert "Полное двоичное представление MAC‑адреса:" in p_texts
    assert "01010000‑10111011‑10110101‑01010000‑00110001‑00110010" in p_texts


def test_search_grounding_citations_cleanup():
    """Verify removal of AI search artifacts and footnotes."""
    md = (
        "# Задание\n\n"
        "Выполнена команда вызова справки [cite: 4]. Получены параметры сетевого адаптера [cite: 1, 2].\n"
        "Сетевая маска подсети [citation: 3] определена верно【1†source】.\n"
    )
    doc = docx.Document(build_docx_report(ReportMetadata(), md))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "[cite:" not in full_text
    assert "[citation:" not in full_text
    assert "†source" not in full_text
    assert "Выполнена команда вызова справки." in full_text
    assert "Получены параметры сетевого адаптера." in full_text


def test_collapse_single_line_command_block():
    """Verify single-line terminal command fences collapse into inline code."""
    md = (
        "# Ход работы\n\n"
        "1. В командной строке выполнена команда:\n"
        "```bash\n"
        "ipconfig /all\n"
        "```\n\n"
        "Результат представлен на рисунке 1.\n"
    )
    doc = docx.Document(build_docx_report(ReportMetadata(), md))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    # Keep the command text without creating a separate listing table or caption.
    assert "ipconfig /all" in full_text
    assert "Листинг" not in full_text


def test_unwrap_pseudo_code_text_blocks():
    """Verify text fences containing equations or lists unwrap into ordinary text."""
    md = (
        "# Ход работы\n\n"
        "Десятичные октеты переведены в двоичную систему:\n"
        "```text\n"
        "- $10_{10} = 00001010_2$;\n"
        "- $30_{10} = 00011110_2$;\n"
        "```\n\n"
        "Вычисления закончены.\n"
    )
    doc = docx.Document(build_docx_report(ReportMetadata(), md))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    # Unwrap the block without creating a listing.
    assert "Листинг" not in full_text
    # Require paragraphs containing native oMath elements.
    omml_paras = [p for p in doc.paragraphs if len(p._p.xpath('.//*[local-name()="oMath"]')) > 0]
    assert len(omml_paras) == 2


def test_unwrap_pseudo_code_text_blocks_preserves_shell_logs():
    """Verify terminal logs with shell prompts remain fenced listings."""
    md = (
        "# Ход работы\n\n"
        "Вывод терминала:\n"
        "```text\n"
        "user@host:~$ ls -la\n"
        "total 4\n"
        "-rw-r--r-- 1 user user 100 Jan 1 00:00 file.txt\n"
        "```\n"
    )
    doc = docx.Document(build_docx_report(ReportMetadata(), md))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    # Keep the code block as a captioned listing.
    assert "Листинг" in full_text
    # Render listing contents inside a table.
    table_texts = "\n".join(cell.text for t in doc.tables for row in t.rows for cell in row.cells)
    assert "user@host:~$ ls -la" in table_texts


def test_typography_number_sign_nbsp():
    """Verify the numero sign binds to its number with NBSP."""
    from app.engine.typography import apply_typography_rules
    res = apply_typography_rules("Лабораторная работа № 5 по дисциплине ИБ")
    assert "№\u00a05" in res


def test_table_preceding_sentence_not_eaten():
    """Verify prose preceding a table is not removed."""
    md = (
        "# Результаты\n\n"
        "Таблица 1 демонстрирует распределение логических адресов хостов в подсети.\n\n"
        "| Хост | IP-адрес |\n"
        "| --- | --- |\n"
        "| PC1 | 10.30.245.1 |\n"
    )
    doc = docx.Document(build_docx_report(ReportMetadata(), md))
    full_text = "\n".join(p.text for p in doc.paragraphs).replace("\xa0", " ")
    # Preserve the user's sentence in the document.
    assert "Таблица 1 демонстрирует распределение логических адресов хостов в подсети." in full_text


def test_linter_no_false_positive_on_narrative_sentences():
    """Verify figure/table references at sentence starts are not mistaken for captions."""
    from app.engine.linter import lint_docx_document
    md = (
        "# Ход работы\n\n"
        "Таблица 1 содержит экспериментальные данные исследования сетевых адаптеров.\n\n"
        "Рисунок 1 иллюстрирует топологию разработанной беспроводной сети.\n"
    )
    bio = build_docx_report(ReportMetadata(), md)
    res = lint_docx_document(bio)
    # These sentences must not trigger trailing-period caption warnings.
    error_msgs = [e.message for e in res.errors]
    assert not any("Обнаружена точка в конце подписи таблицы" in m for m in error_msgs)
    assert not any("Обнаружена точка в конце подписи рисунка" in m for m in error_msgs)


def test_formula_explication_and_standalone_code_formatting():
    """Verify equation-explanation and standalone-code paragraph formatting."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    md = (
        "# Расчеты\n\n"
        "Обычный абзац текста перед вычислением параметров.\n\n"
        "$$N = 2^n - 2$$\n\n"
        "где $n$ — количество бит в узловой части адреса ($n = 8$).\n\n"
        "`00001010.00011110.11110101.01110011`\n"
    )
    bio = build_docx_report(ReportMetadata(), md)
    doc = docx.Document(bio)
    
    # Ordinary prose uses firstLine="709".
    p_norm = [p for p in doc.paragraphs if "Обычный абзац" in p.text][0]
    p_norm_ind = p_norm._p.pPr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ind')
    assert p_norm_ind.attrib.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}firstLine') == "709"

    # Equation explanations use firstLine="0" under GOST 7.32 / GOST 2.105.
    p_explication = [p for p in doc.paragraphs if p.text.startswith("где")][0]
    p_exp_ind = p_explication._p.pPr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ind')
    assert p_exp_ind.attrib.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}firstLine') == "0"

    # Standalone code is centered with firstLine="0".
    p_code = [p for p in doc.paragraphs if "00001010" in p.text][0]
    p_code_ind = p_code._p.pPr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ind')
    assert p_code_ind.attrib.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}firstLine') == "0"
    assert p_code.alignment == WD_ALIGN_PARAGRAPH.CENTER


def test_logo_mode_none_generates_clean_title_page():
    """Verify logo-free title-page generation under GOST 2.105."""
    meta = ReportMetadata(
        university="Государственный технический университет",
        institute="Информатика и системы управления",
        department="Программное обеспечение ЭВМ и информационные технологии",
        logo_mode="none",
        city="Москва"
    )
    md = "# 1. Ход работы\n\nБыла выполнена проверка универсального титульного листа."
    bio = build_docx_report(meta, md)
    doc = docx.Document(bio)

    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert meta.university in full_text
    assert "Москва" in full_text
    # The title page must not contain an anchored logo.
    anchors = doc.paragraphs[0]._p.xpath('.//*[local-name()="anchor"]')
    assert len(anchors) == 0

    # Audit generated output for compliance.
    lint_res = lint_docx_document(bio)
    assert lint_res.score == 100
    assert lint_res.is_valid is True









def test_bibliography_formats_gost_r_705():
    from app.engine.bibliography import format_reference
    book = format_reference({
        "kind": "book", "authors": "И.И. Иванов", "title": "Основы сетей",
        "place": "М.", "publisher": "Техника", "year": "2024", "details": "256 с."
    })
    assert book == "И.И.\u00A0Иванов. Основы сетей.\u00A0— М.: Техника, 2024.\u00A0— 256\u00A0с."
    article = format_reference({
        "kind": "article", "authors": "П.П. Петров", "title": "Анализ трафика",
        "publisher": "Сети и связь", "year": "2024", "details": "№ 3. – С. 12–18"
    })
    assert article == "П.П.\u00A0Петров. Анализ трафика // Сети и\u00A0связь.\u00A0— 2024.\u00A0— №\u00A03.\u00A0— С.\u00A012–18."
    site = format_reference({
        "kind": "website", "title": "Учебный ресурс", "url": "https://example.com", "details": "24.09.2026"
    })
    assert site == "Учебный ресурс : [Электронный ресурс].\u00A0— URL: https://example.com (дата обращения: 24.09.2026)."
    std = format_reference({
        "kind": "standard", "title": "ГОСТ 7.32-2017. Отчёт о НИР",
        "place": "М.", "publisher": "Стандартинформ", "year": "2017", "details": "32 с."
    })
    assert std == "ГОСТ 7.32-2017. Отчёт о\u00A0НИР.\u00A0— М.: Стандартинформ, 2017.\u00A0— 32\u00A0с."
    # Empty and malformed entries must not crash the formatter.
    assert format_reference({}) == "Источник"
    assert format_reference({"kind": "unknown-kind", "title": "X"}) == "X."


def test_generate_with_references_keeps_gost_score():
    from app.models.report import Reference
    meta = ReportMetadata(
        work_theme="Тестовая работа",
        discipline="Физика",
        references=[
            Reference(kind="book", authors="И.И. Иванов", title="Основы сетей",
                      place="М.", publisher="Техника", year="2024", details="256 с."),
            Reference(kind="website", title="Учебный ресурс", url="https://example.com", details="24.09.2026"),
        ]
    )
    md = "# Цель работы\nИзучить сети [1].\n\n# Ход работы\nПроведено изучение.\n\n# Вывод\nСети изучены."
    bio = build_docx_report(meta, md)
    doc = docx.Document(bio)
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ" in full_text
    assert "1.\u00A0И.И.\u00A0Иванов. Основы сетей." in full_text
    assert "2.\u00A0Учебный ресурс : [Электронный ресурс]." in full_text
    lint_res = lint_docx_document(bio)
    assert lint_res.score == 100
    assert lint_res.is_valid is True


def _solid_png(width: int, height: int) -> bytes:
    import struct, zlib
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def test_image_size_from_headers():
    from app.engine.markdown_parser import _image_size
    assert _image_size(_solid_png(100, 2000)) == (100, 2000)
    assert _image_size(b"not an image") is None
    assert _image_size(b"GIF89a\x05\x00\x03\x00\x00\x00\x00") == (5, 3)


def test_tall_image_height_capped_in_docx():
    from docx.shared import Mm
    meta = ReportMetadata(work_theme="T", discipline="D")
    tall = _solid_png(100, 2000)  # Use a 1:20 aspect ratio.
    bio = build_docx_report(meta, "# Ход работы\n\n![Длинный скриншот](tall.png)\n", images_dict={"tall.png": tall})
    doc = docx.Document(bio)
    pic = doc.inline_shapes[0]
    assert pic.height <= Mm(200) + 1000  # Allow EMU rounding tolerance.
    assert pic.width < Mm(155)  # Reduce width proportionally.


def test_figure_caption_has_visible_space_before_following_paragraph():
    from docx.oxml.ns import qn
    meta = ReportMetadata(work_theme="T", discipline="D")
    doc = docx.Document(build_docx_report(
        meta,
        "# Ход работы\n\n![Схема](figure.png)\n\nТекст после рисунка.",
        images_dict={"figure.png": b"not-image"},
    ))
    caption = next(p for p in doc.paragraphs if p.text.startswith("Рисунок"))
    following = next(p for p in doc.paragraphs if p.text == "Текст после рисунка.")
    caption_spacing = caption._p.find(qn("w:pPr")).find(qn("w:spacing"))
    following_spacing = following._p.find(qn("w:pPr")).find(qn("w:spacing"))
    assert caption_spacing.get(qn("w:after")) == "240"
    assert following_spacing.get(qn("w:before")) == "0"


def test_per_image_layout_controls_width_height_alignment_and_page_break():
    from docx.shared import Mm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    meta = ReportMetadata(image_layouts={
        "wide.png": {"width_percent": 72, "align": "right", "page_break_before": True},
        "tall.png": {"width_percent": 90, "max_height_mm": 80},
    })
    markdown = "# Ход работы\n\n![Схема](wide.png)\n\n![Снимок](tall.png)"
    images = {"wide.png": _solid_png(500, 100), "tall.png": _solid_png(100, 1000)}
    doc = docx.Document(build_docx_report(meta, markdown, images_dict=images))
    assert abs(doc.inline_shapes[0].width - Mm(165 * .72)) < Mm(.5)
    assert doc.inline_shapes[1].height <= Mm(80) + 1000
    image_paragraph = next(p for p in doc.paragraphs if p._p.xpath('.//w:drawing'))
    assert image_paragraph.alignment == WD_ALIGN_PARAGRAPH.RIGHT
    assert image_paragraph._p.xpath('./w:pPr/w:pageBreakBefore')
    assert image_paragraph._p.xpath('./w:pPr/w:keepNext')


def test_layout_matches_sanitized_name_of_cyrillic_image_with_spaces():
    from docx.shared import Mm
    image = _solid_png(400, 100)
    meta = ReportMetadata(image_layouts={"Схема_сети.png": {"width_percent": 60}})
    doc = docx.Document(build_docx_report(
        meta, "![Рисунок 1 — Схема](<Схема сети.png>)", images_dict={"Схема сети.png": image}
    ))
    assert len(doc.inline_shapes) == 1
    assert abs(doc.inline_shapes[0].width - Mm(99)) < Mm(.5)


def test_structure_warning_for_missing_conclusion():
    meta = ReportMetadata(work_theme="T", discipline="D")
    bio = build_docx_report(meta, "# Цель работы\nЦель.\n\n# Ход работы\nХод.")
    res = lint_docx_document(bio)
    struct = [w for w in res.warnings if w.type == "STRUCTURE"]
    assert len(struct) == 1
    assert "Вывод" in struct[0].message


def test_structure_silent_for_full_trio_and_custom_docs():
    meta = ReportMetadata(work_theme="T", discipline="D")
    full = build_docx_report(meta, "# Цель работы\nЦ.\n\n# Ход работы\nХ.\n\n# Вывод\nВ.")
    assert not [w for w in lint_docx_document(full).warnings if w.type == "STRUCTURE"]
    custom = build_docx_report(meta, "# Введение\nВ.\n\n# Глава 1\nТекст.")
    assert not [w for w in lint_docx_document(custom).warnings if w.type == "STRUCTURE"]


def test_structure_section_name_variants():
    # Singular, plural, numbered headings — all must count as the section
    from app.engine.linter import lint_docx_document
    meta = ReportMetadata(work_theme="T", discipline="D")

    variants = [
        "# Цели работы\nЦ.\n\n# Ход работы\nХ.\n\n# Выводы\nВ.",  # plural
        "# 1. Цель работы\nЦ.\n\n# 2. Ход работы\nХ.\n\n# 3. Вывод\nВ.",  # numbered
        "# Цель: исследование\nЦ.\n\n# Ход работы\nХ.\n\n# Вывод\nВ.",  # colon
    ]
    for md in variants:
        bio = build_docx_report(meta, md)
        struct = [w for w in lint_docx_document(bio).warnings if w.type == "STRUCTURE"]
        assert struct == [], md


def test_manual_dotted_figure_numbering_preserved():
    """Verify compound manual numbers remain verbatim in the author's order."""
    md = (
        "![Рисунок 4.2 — Схема стенда](a.png)\n\n"
        "![Рисунок 4.3 — План сети](b.png)\n\n"
        "![Рисунок 4.1 — График](c.png)"
    )
    doc = docx.Document(build_docx_report(ReportMetadata(), md))
    caps = [p.text for p in doc.paragraphs if p.text.startswith("Рисунок")]
    assert caps == [
        "Рисунок\u00A04.2 — Схема стенда",
        "Рисунок\u00A04.3 — План сети",
        "Рисунок\u00A04.1 — График",
    ]


def test_manual_dotted_number_from_separate_caption_line():
    """Verify a number in a separate caption below an image is preserved verbatim."""
    md = "# Раздел\n\n![Схема сети](net.png)\nРисунок 4.2 — Схема сети\n\nТекст."
    doc = docx.Document(build_docx_report(ReportMetadata(), md))
    caps = [p.text for p in doc.paragraphs if p.text.startswith("Рисунок")]
    assert caps == ["Рисунок\u00A04.2 — Схема сети"]


def test_manual_dotted_table_numbering_preserved():
    """Verify compound manual table numbers are preserved verbatim."""
    md = "Таблица 4.2 — Параметры\n\n| A |\n|---|\n| 1 |"
    doc = docx.Document(build_docx_report(ReportMetadata(), md))
    caps = [p.text for p in doc.paragraphs if p.text.startswith("Таблица")]
    assert len(caps) == 1
    assert caps[0] == "Таблица\u00A04.2 — Параметры"


def test_find_missing_images():
    """Detect missing attachments while excluding fenced code and external URLs."""
    from app.engine.markdown_parser import find_missing_images
    md = (
        "![Схема](a.png)\n\n"
        "![План](b.png)\n\n"
        "```\n![Не рисунок](c.png)\n```\n\n"
        "![Внешняя](https://example.com/x.png)\n"
    )
    assert find_missing_images(md, {"a.png": b"fake"}) == ["b.png"]


def test_linter_missing_image_placeholder_warning():
    """Verify missing-image placeholders produce IMAGES warnings."""
    md = "# Цель работы\nЦ.\n\n# Ход работы\nХ.\n\n# Вывод\nВ.\n\n![Схема сети](net.png)\n"
    res = lint_docx_document(build_docx_report(ReportMetadata(), md))
    assert any(w.type == "IMAGES" and "net.png" in w.message for w in res.warnings)


def test_linter_dotted_figure_reference_no_false_warning():
    """Verify a prose reference satisfies REFERENCE for a compound figure number."""
    md = (
        "# Цель работы\nЦ.\n\n# Ход работы\nКак представлено на рисунке 4.2.\n\n"
        "# Вывод\nВ.\n\n![Рисунок 4.2 — Схема](a.png)\n"
    )
    res = lint_docx_document(build_docx_report(ReportMetadata(), md))
    assert not [w for w in res.warnings if w.type == "REFERENCE" and "4.2" in w.location]


def test_linter_figure_range_covers_each_caption_without_explicit_mentions():
    md = (
        "# Цель работы\nЦель.\n\n# Ход работы\nСхемы показаны на рисунках 12–14.\n\n"
        "![Рисунок 12 — Первый](a.png)\n\n"
        "![Рисунок 13 — Второй](b.png)\n\n"
        "![Рисунок 14 — Третий](c.png)\n\n# Вывод\nИтог."
    )
    images = {name: _solid_png(12, 12) for name in ("a.png", "b.png", "c.png")}
    res = lint_docx_document(build_docx_report(ReportMetadata(), md, images_dict=images))
    assert res.metrics.figures_count == 3
    assert not [w for w in res.warnings if w.type == "REFERENCE" and "Рисунок" in w.location]


def test_linter_prose_beginning_with_vyvod_is_not_a_heading():
    md = "# Цель работы\nЦель.\n\n# Ход работы\nВывод программы записан в файл.\n\n# Вывод\nИтог."
    res = lint_docx_document(build_docx_report(ReportMetadata(), md))
    assert not [e for e in res.errors if e.type == "PUNCTUATION" and "Вывод программы" in e.message]


def test_linter_flags_internal_path_in_report_prose():
    md = "# Цель работы\nЦель.\n\n# Ход работы\nСнимки взяты из /home/student/edits.\n\n# Вывод\nИтог."
    res = lint_docx_document(build_docx_report(ReportMetadata(), md))
    assert any(w.type == "INTERNAL_NOTES" for w in res.warnings)


def test_linter_detects_caption_without_an_image():
    md = "# Ход работы\n\nРисунок 5 — Несуществующая схема\n\n# Вывод\nИтог."
    res = lint_docx_document(build_docx_report(ReportMetadata(), md))
    assert any(w.type == "IMAGES" and "Рисунок 5" in w.message for w in res.warnings)


def test_linter_warns_when_a_compound_figure_number_is_missing():
    images = {name: _solid_png(10, 10) for name in ("a.png", "c.png")}
    md = ("# Ход работы\nНа рисунке 4.1 показан код, на рисунке 4.3 — вывод.\n\n"
          "![Рисунок 4.1 — Код](a.png)\n\n![Рисунок 4.3 — Вывод](c.png)")
    res = lint_docx_document(build_docx_report(ReportMetadata(), md, images_dict=images))
    assert any(w.type == "NUMBERING" and "4.2" in w.message for w in res.warnings)
