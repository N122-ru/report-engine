from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional

class StudentInfo(BaseModel):
    fio: str = Field(default="", description="И.О. Фамилия студента (И.О. Фамилия или Фамилия И.О.)")
    group: str = Field(default="", description="Академическая группа")

class TeacherInfo(BaseModel):
    fio: str = Field(default="", description="И.О. Фамилия преподавателя")
    role: str = Field(default="ст. преп.", description="Должность (преп., ст. преп., доцент, профессор)")

class Reference(BaseModel):
    id: str = Field(default="", description="Локальный идентификатор записи")
    kind: str = Field(default="book", description="Тип: book | article | website | standard")
    authors: str = Field(default="", description="Авторы (И.О. Фамилия)")
    title: str = Field(default="", description="Название")
    place: str = Field(default="", description="Место издания")
    publisher: str = Field(default="", description="Издательство / журнал")
    year: str = Field(default="", description="Год")
    details: str = Field(default="", description="Страницы, номер, дата обращения")
    url: str = Field(default="", description="URL для электронных ресурсов")

class ImageLayout(BaseModel):
    width_percent: float = Field(default=94, ge=10, le=100)
    max_height_mm: float = Field(default=200, ge=30, le=220)
    align: Literal["center", "left", "right"] = "center"
    keep_caption_with_image: bool = True
    page_break_before: bool = False

class ReportMetadata(BaseModel):
    university: str = Field(
        default="",
        description="Полное наименование университета"
    )
    ministry: str = Field(
        default="МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ РОССИЙСКОЙ ФЕДЕРАЦИИ"
    )
    logo_mode: str = Field(
        default="none",
        description="Режим логотипа: default (встроенный) | custom (свой файл) | none (без логотипа, ГОСТ 2.105)"
    )
    custom_logo: Optional[str] = Field(
        default=None,
        description="Пользовательский логотип (base64 или имя файла)"
    )
    institute: str = Field(
        default=""
    )
    department: str = Field(
        default=""
    )
    doc_type: str = Field(
        default="ОТЧЕТ"
    )
    work_type: str = Field(
        default="о выполнении лабораторной работы"
    )
    work_number: int = Field(default=1)
    work_theme: str = Field(default="")
    discipline: str = Field(default="")
    students: List[StudentInfo] = Field(
        default_factory=lambda: [StudentInfo(fio="", group="")]
    )
    references: List[Reference] = Field(
        default_factory=list,
        description="Список использованных источников (ГОСТ Р 7.0.5)"
    )
    image_layouts: Dict[str, ImageLayout] = Field(default_factory=dict)
    teachers: List[TeacherInfo] = Field(
        default_factory=lambda: [TeacherInfo(fio="", role="ст. преп.")]
    )
    city: str = Field(default="")
    year: int = Field(default=2026)
    heading_alignment: str = Field(default="center", description="Выравнивание заголовков разделов (center — ГОСТ 7.32 | left — методички)")
    page_numbering: str = Field(default="center", description="Нумерация страниц (center | right | none)")
    page_break_before_h1: bool = Field(default=False, description="Разрыв страницы перед каждым разделом 1-го уровня")
    hide_captions: bool = Field(default=False, description="Не вставлять подписи к рисункам и листингам")
    custom_instructions: Optional[str] = Field(default="", description="Кастомные требования (только для ИИ-промптов, на DOCX не влияют)")
    prompt_latex: Optional[bool] = Field(default=True, description="Требовать ли формулы LaTeX в ИИ-промптах (на DOCX не влияет)")
    prompt_code_blocks: Optional[bool] = Field(default=False, description="Разрешать ли блоки текста и кода ``` (на DOCX не влияет)")
    latex_mode: Optional[str] = Field(default="omml", description="Формулы LaTeX: omml (нативные) | unicode (нарочно упрощённый текст)")

class GenerateOptions(BaseModel):
    include_title_page: bool = True
    page_break_before_h1: Optional[bool] = None
    heading_alignment: Optional[str] = None # Center under GOST 7.32; left for department guides.
    page_numbering: Optional[str] = None # Center under GOST 7.32; right under GOST 2.105; or none.
    hide_captions: Optional[bool] = None # Omit figure and listing captions.
    latex_mode: Optional[str] = None # Native OMML equations or simplified Unicode text.
