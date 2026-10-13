"""Route MCP calls and synchronize report sessions over SSE.

Remote agents connect to the user's session using the MCP SSE transport.
"""

import sys
import os
import io
import json
import re
import time
import uuid
import asyncio
import base64
import binascii
import mimetypes
import hashlib
import difflib
from markdown_it import MarkdownIt
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, Request, Response, HTTPException, Query, Body, UploadFile, File
from fastapi.responses import StreamingResponse

from .sessions import session_manager, SessionData, MAX_IMAGE_SIZE, MAX_IMAGES_COUNT
from .security import MAX_MARKDOWN_SIZE
from ..models.report import ReportMetadata, GenerateOptions, ImageLayout
from .generator import build_docx_report
from .linter import lint_docx_document
from .typography import apply_typography_outside_code, strip_trailing_dot
from .section_editor import edit_section, sections, section_identifier
from .block_editor import blocks, edit_block, move_figure
from .profile import load_profile_input, profile_metadata
from ..version import APP_VERSION

router = APIRouter()

# Active MCP SSE connections map connection IDs to asyncio queues.
_mcp_connections: Dict[str, asyncio.Queue] = {}


def _load_skill_text() -> str:
    """Load canonical agent instructions from assets/SKILL.md."""
    candidates = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "SKILL.md")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "SKILL.md")),
        os.path.abspath("assets/SKILL.md"),
        os.path.abspath("SKILL.md"),
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read().strip()
        except Exception:
            continue
    return ""


def _decode_image_data(encoded: str, filename: str) -> bytes:
    if "base64," in encoded[:50]:
        encoded = encoded.split(",", 1)[1]
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"Некорректные данные изображения {filename}: {exc}") from exc
    if not data or len(data) > MAX_IMAGE_SIZE:
        raise ValueError(f"Размер изображения {filename} выходит за пределы 1–{MAX_IMAGE_SIZE} байт")
    return data


def _apply_content_patches(content: str, patches: Any) -> str:
    if not isinstance(patches, list) or not 1 <= len(patches) <= 200:
        raise HTTPException(status_code=422, detail="content_patches должен содержать от 1 до 200 операций")
    normalized = []
    for patch in patches:
        if (not isinstance(patch, dict)
                or not isinstance(patch.get("start"), int)
                or not isinstance(patch.get("delete_count"), int)
                or not isinstance(patch.get("insert"), str)):
            raise HTTPException(status_code=422, detail="Некорректная операция content_patches")
        start = patch["start"]
        delete_count = patch["delete_count"]
        if start < 0 or delete_count < 0:
            raise HTTPException(status_code=422, detail="Индексы content_patches не могут быть отрицательными")
        normalized.append((start, delete_count, patch["insert"]))

    ordered = sorted(normalized)
    previous_end = 0
    content_length = len(content)
    for start, delete_count, _ in ordered:
        if start < previous_end or start + delete_count > content_length:
            raise HTTPException(status_code=422, detail="Диапазоны content_patches пересекаются или выходят за границы")
        previous_end = start + delete_count

    result = content
    for start, delete_count, insert in reversed(ordered):
        result = result[:start] + insert + result[start + delete_count:]
    if len(result.encode("utf-8")) > MAX_MARKDOWN_SIZE:
        raise HTTPException(status_code=413, detail="Размер текста отчета превышает допустимый лимит (500 КБ)")
    return result


# ==============================================================================
# MCP Tools Manifest
# ==============================================================================

MCP_LIVE_TOOLS = [
    {
        "name": "list_images",
        "description": (
            "Возвращает список всех прикрепленных к отчету изображений и скриншотов, размеры в пикселях и байтах, MIME-типы "
            "SHA-256 и флаг is_in_report (вставлена ли уже картинка в Markdown-текст отчета). "
            "Вызывай этот инструмент, чтобы увидеть, какие скриншоты студент загрузил со стенда."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_image",
        "description": (
            "Возвращает изображение/скриншот в бинарном формате (MCP Image Content). "
            "Используй этот инструмент, чтобы получить визуальное содержимое скриншота "
            "(вывод терминала, схемы сетей, графики, осциллограммы) "
            "и отразить фактические данные в отчете."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["filename"],
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Имя файла изображения (из списка list_images), например 'screenshot1.png'"
                }
            }
        }
    },
    {
        "name": "get_images",
        "description": (
            "Пакетно возвращает несколько изображений одним MCP-вызовом. "
            "Используй после list_images для контактного листа или выборочной проверки "
            "уникальных ключевых скриншотов; не запрашивай один файл повторно без причины."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["filenames"],
            "properties": {
                "filenames": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 16,
                    "items": {"type": "string"},
                    "description": "Имена файлов из list_images, максимум 16 за один вызов"
                }
            }
        }
    },
    {
        "name": "upload_image",
        "description": (
            "Загружает изображение (график matplotlib, схему) в сессию отчета. "
            "Изображение отображается в браузере в панели медиа и на страницах макета А4. "
            "Принимает имя файла и данные base64. Опционально может сразу вставить ссылку в Markdown."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["filename", "base64_data", "expected_revision"],
            "properties": {
                "expected_revision": {"type": "string", "description": "Текущая revision из get_report_state"},
                "filename": {
                    "type": "string",
                    "description": "Имя файла с расширением, например 'plot_response.png' или 'topology.png'"
                },
                "base64_data": {
                    "type": "string",
                    "description": "Бинарные данные изображения, закодированные в Base64"
                },
                "caption": {
                    "type": "string",
                    "description": "Опционально: подпись к рисунку по ГОСТ, например 'Временная диаграмма сигнала'"
                },
            "insert_into_report": {
                    "type": "boolean",
                    "default": False,
                    "description": "Если true, автоматически добавляет ![caption](filename) в конец отчета"
                }
            }
        }
    },
    {
        "name": "upload_images",
        "description": "Атомарно загружает несколько рисунков и при необходимости вставляет их после блоков из текущего outline.",
        "inputSchema": {
            "type": "object", "required": ["images", "expected_revision"],
            "properties": {
                "expected_revision": {"type": "string"},
                "images": {
                    "type": "array", "minItems": 1, "maxItems": MAX_IMAGES_COUNT,
                    "items": {
                        "type": "object", "required": ["filename", "base64_data"],
                        "properties": {
                            "filename": {"type": "string"}, "base64_data": {"type": "string"},
                            "caption": {"type": "string"}, "after_block_id": {"type": "string"}
                        }
                    }
                }
            }
        }
    },
    {
        "name": "update_image_layout",
        "description": "Настраивает размер и размещение одного прикреплённого рисунка без правки Markdown.",
        "inputSchema": {
            "type": "object", "required": ["filename", "expected_meta_revision"],
            "properties": {
                "filename": {"type": "string"},
                "expected_meta_revision": {"type": "string", "description": "Текущая meta_revision из get_report_state"},
                "width_percent": {"type": "number", "minimum": 10, "maximum": 100},
                "max_height_mm": {"type": "number", "minimum": 30, "maximum": 220},
                "align": {"type": "string", "enum": ["center", "left", "right"]},
                "keep_caption_with_image": {"type": "boolean"},
                "page_break_before": {"type": "boolean"}
            }
        }
    },
    {
        "name": "get_report_state",
        "description": (
            "Получает текущий текст Markdown, тему и реквизиты титульного листа отчёта прямо из открытой вкладки браузера студента. "
            "Также отдаёт headings, revision, meta_revision и image_revision для безопасных точечных правок. "
            "Вызывай перед началом работы и после конфликта."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "append_or_update_section",
        "description": (
            "Добавляет или обновляет раздел отчёта (например '## 1. Ход работы', '## 2. Результаты', '# Цель работы'). "
            "Границы раздела определяются Markdown-заголовками; одинаковые заголовки отклоняются. "
            "Передавай expected_revision из get_report_state. Ответ содержит diff и списки headings_before/headings_after. "
            "Изменения синхронизируются с предпросмотром макета А4 без перезаписи всего документа. "
            "Правила ГОСТ 7.32: "
            "1) Безличный стиль («выполнено», «настроено», «рассчитано», «исследовано»). Без местоимений 'я' и 'мы'. "
            "2) Иллюстрации вставляются через ![Название рисунка](имя_файла.png). Не дублировать подпись отдельной текстовой строкой. "
            "3) Формулы оформляются выключными строками $$...$$ или инлайн $...$. Не использовать блоки ```text для расчетов. "
            "4) Краткое техническое назначение элементов (1 строка контекста), без избыточной теории."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["section_heading", "section_content", "expected_revision"],
            "properties": {
                "section_heading": {
                    "type": "string",
                    "description": "Заголовок раздела со знаками решетки, например '## 1. Ход работы' или '# Цель работы'"
                },
                "section_content": {
                    "type": "string",
                    "description": "Текст раздела на Markdown по правилам ГОСТ 7.32 (без повторного дублирования заголовка)"
                },
                "mode": {
                    "type": "string",
                    "enum": ["update_or_append", "replace_body", "append_to_body", "replace", "append"],
                    "default": "update_or_append",
                    "description": "replace_body — только существующий раздел; append_to_body — в конец тела существующего раздела; update_or_append — создать, если раздела нет. replace/append — старые синонимы."
                },
                "expected_revision": {
                    "type": "string",
                    "description": "Обязательная SHA-256 revision из get_report_state; предотвращает запись поверх новых правок"
                },
                "section_id": {
                    "type": "string",
                    "description": "Необязательный ID конкретного раздела из get_document_outline; позволяет адресовать одинаковые заголовки"
                }
            }
        }
    },
    {
        "name": "patch_text",
        "description": (
            "Точечно заменяет одну уникальную фразу в Markdown без пересборки раздела. "
            "Передавай expected_revision из get_report_state; если фраза не уникальна, операция отклоняется."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["find", "replace", "expected_revision"],
            "properties": {
                "find": {"type": "string", "description": "Точный фрагмент, который нужно найти ровно один раз"},
                "replace": {"type": "string", "description": "Новый текст"},
                "expected_revision": {"type": "string", "description": "SHA-256 revision из get_report_state"}
            }
        }
    },
    {
        "name": "apply_patches",
        "description": "Атомарно применяет несколько непересекающихся уникальных текстовых замен; при любой ошибке отчёт не меняется.",
        "inputSchema": {
            "type": "object", "required": ["expected_revision", "patches"],
            "properties": {
                "expected_revision": {"type": "string"},
                "patches": {"type": "array", "minItems": 1, "maxItems": 100,
                            "items": {"type": "object", "required": ["find", "replace"],
                                      "properties": {"find": {"type": "string"}, "replace": {"type": "string"}}}}
            }
        }
    },
    {
        "name": "get_document_outline",
        "description": "Перечисляет разделы и блоки с идентификаторами, действительными только для текущей revision.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "replace_block",
        "description": "Заменяет ровно один Markdown-блок по ID из get_document_outline; сохраняет соседние блоки.",
        "inputSchema": {
            "type": "object", "required": ["block_id", "content", "expected_revision"],
            "properties": {
                "block_id": {"type": "string"}, "content": {"type": "string"},
                "expected_revision": {"type": "string"}
            }
        }
    },
    {
        "name": "delete_block",
        "description": "Удаляет один абзац, рисунок, элемент списка или блок кода по ID текущей revision.",
        "inputSchema": {
            "type": "object", "required": ["block_id", "expected_revision"],
            "properties": {"block_id": {"type": "string"}, "expected_revision": {"type": "string"}}
        }
    },
    {
        "name": "move_figure",
        "description": "Перемещает рисунок перед указанным блоком, сохраняя заголовки и требуя актуальную revision.",
        "inputSchema": {
            "type": "object", "required": ["block_id", "before_block_id", "expected_revision"],
            "properties": {
                "block_id": {"type": "string"}, "before_block_id": {"type": "string"},
                "expected_revision": {"type": "string"}
            }
        }
    },
    {
        "name": "get_last_edit",
        "description": "Показывает diff последней правки текста, источник изменения и версии до/после.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_edit_history",
        "description": "Показывает последние 20 правок текста с отметками времени и версиями.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "rollback_last_edit",
        "description": "Откатывает только последнюю правку текста агента при совпадении текущей версии. Правки студента не откатывает.",
        "inputSchema": {
            "type": "object", "required": ["expected_revision"],
            "properties": {"expected_revision": {"type": "string", "description": "Актуальная revision из get_report_state"}}
        }
    },
    {
        "name": "lint_report",
        "description": (
            "Выполняет строгий аудит отчета по ГОСТ 7.32 (шрифт 14 pt Times New Roman, поля 30/15/20/20 мм, "
            "точки в заголовках, подписи к рисункам и таблицам). Возвращает статус ready/needs_review/invalid, оценку 0-100 и замечания."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "markdown_content": {
                    "type": "string",
                    "description": "Опционально: проверить конкретный текст вместо текущего отчета"
                },
                "expected_task_count": {"type": "integer", "minimum": 0, "description": "Число заданий из методички для сверки с текстом"},
                "expected_figures_count": {"type": "integer", "minimum": 0, "description": "Ожидаемое количество рисунков для сверки"}
            }
        }
    },
    {
        "name": "autofix_typography",
        "description": (
            "Применяет ГОСТ-типографику к прозе отчета, сохраняя Markdown-ссылки и код. "
            "Требует текущую revision; возвращает diff и новую revision."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["expected_revision"],
            "properties": {"expected_revision": {"type": "string"}}
        }
    },
    {
        "name": "update_meta",
        "description": (
            "Точечно обновляет реквизиты титульного листа и параметры работы (тема, номер, вид работы, "
            "дисциплина, институт, кафедра, вуз, город, год, преподаватели, студенты, указания преподавателя). "
            "Передавай только изменяемые поля, остальное сохранится. Изменения сразу видны в браузере. "
            "Так агент сам заполняет шапку отчета: выбирает дисциплину, кафедру и преподавателя без участия студента."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["expected_meta_revision"],
            "properties": {
                "work_theme": {"type": "string", "description": "Тема работы"},
                "work_number": {"type": "integer", "description": "Номер работы"},
                "work_type": {"type": "string", "description": "Вид работы (например 'о выполнении лабораторной работы')"},
                "discipline": {"type": "string", "description": "Название дисциплины"},
                "institute": {"type": "string", "description": "Факультет / институт"},
                "department": {"type": "string", "description": "Кафедра"},
                "university": {"type": "string", "description": "Полное наименование университета"},
                "ministry": {"type": "string", "description": "Министерство (ведомство)"},
                "city": {"type": "string", "description": "Город"},
                "year": {"type": "integer", "description": "Год"},
                "teachers": {
                    "type": "array",
                    "description": "Проверяющие: список {fio: 'И.О. Фамилия', role: должность}",
                    "items": {"type": "object"}
                },
                "students": {
                    "type": "array",
                    "description": "Авторы: список {fio: 'И.О. Фамилия', group: группа}",
                    "items": {"type": "object"}
                },
                "custom_instructions": {"type": "string", "description": "Указания преподавателя"},
                "expected_meta_revision": {"type": "string", "description": "Версия реквизитов из get_report_state; защищает от перезаписи новых правок"},
                "references": {
                    "type": "array",
                    "description": "Источники: полный список {kind: book|article|website|standard, authors, title, place, publisher, year, details, url} (заменяет целиком, передавай весь массив)",
                    "items": {"type": "object"}
                }
            }
        }
    },
    {
        "name": "import_profile",
        "description": (
            "Импортирует профиль дисциплины и титульного листа формата report-engine-profile версии 1. "
            "Принимает JSON-объект profile или путь к локальному JSON-файлу. Требует свежую meta_revision."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["expected_meta_revision"],
            "properties": {
                "profile": {"type": "object", "description": "Объект профиля report-engine-profile версии 1"},
                "file_path": {"type": "string", "description": "Путь к JSON-файлу относительно текущего каталога"},
                "expected_meta_revision": {"type": "string", "description": "Версия реквизитов из get_report_state"},
            }
        }
    },
    {
        "name": "delete_image",
        "description": (
            "Удаляет неиспользуемое изображение при совпадении revision текста и image_revision; "
            "прикреплённые к отчёту рисунки сначала нужно убрать из Markdown."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["filename", "expected_revision", "expected_image_revision"],
            "properties": {
                "expected_revision": {"type": "string"},
                "expected_image_revision": {"type": "string"},
                "filename": {
                    "type": "string",
                    "description": "Имя файла изображения (из списка list_images)"
                }
            }
        }
    },
    {
        "name": "delete_images",
        "description": (
            "Атомарно удаляет несколько неиспользуемых изображений одним вызовом. "
            "Передавай только файлы с is_in_report=false из свежего list_images; "
            "если хотя бы один файл используется в Markdown, пакет отклоняется целиком."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["filenames", "expected_revision", "expected_image_revision"],
            "properties": {
                "filenames": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": MAX_IMAGES_COUNT,
                    "items": {"type": "string"}
                },
                "expected_revision": {"type": "string"},
                "expected_image_revision": {"type": "string"}
            }
        }
    }
]

MCP_TOOL_PAGE_SIZE = 10
MCP_TOOL_CURSOR_PREFIX = "report-live-tools-v1:"

# Keep the complete legacy workflow on the first page. Older clients that do
# not follow nextCursor still retain enough tools to create and validate a
# report; newer clients discover the advanced editors on later pages.
MCP_CORE_TOOL_NAMES = (
    "list_images",
    "get_image",
    "get_images",
    "upload_image",
    "get_report_state",
    "append_or_update_section",
    "lint_report",
    "autofix_typography",
    "update_meta",
    "delete_image",
)

MCP_MUTATING_TOOLS = frozenset({
    "upload_image",
    "upload_images",
    "update_image_layout",
    "append_or_update_section",
    "patch_text",
    "apply_patches",
    "replace_block",
    "delete_block",
    "move_figure",
    "rollback_last_edit",
    "autofix_typography",
    "update_meta",
    "import_profile",
    "delete_image",
    "delete_images",
})


def _ordered_mcp_tools() -> List[Dict[str, Any]]:
    """Return a stable discovery order with the compatible core first."""
    by_name = {tool["name"]: tool for tool in MCP_LIVE_TOOLS}
    core = [by_name[name] for name in MCP_CORE_TOOL_NAMES]
    advanced = [tool for tool in MCP_LIVE_TOOLS if tool["name"] not in MCP_CORE_TOOL_NAMES]
    return core + advanced


def _mcp_tools_page(cursor: Any) -> Dict[str, Any]:
    """Build one paginated tools/list result using an opaque cursor."""
    offset = 0
    if cursor not in (None, ""):
        if not isinstance(cursor, str) or not cursor.startswith(MCP_TOOL_CURSOR_PREFIX):
            raise ValueError("Некорректный cursor для tools/list")
        raw_offset = cursor[len(MCP_TOOL_CURSOR_PREFIX):]
        if not raw_offset.isdigit():
            raise ValueError("Некорректный cursor для tools/list")
        offset = int(raw_offset)

    tools = _ordered_mcp_tools()
    if offset < 0 or offset > len(tools):
        raise ValueError("Cursor tools/list указывает за пределы списка инструментов")

    end = min(offset + MCP_TOOL_PAGE_SIZE, len(tools))
    result: Dict[str, Any] = {"tools": tools[offset:end]}
    if end < len(tools):
        result["nextCursor"] = f"{MCP_TOOL_CURSOR_PREFIX}{end}"
    return result


# ==============================================================================
# Tool handlers operate on the selected user session.
# ==============================================================================

async def _dispatch_mcp_tool(tool_name: str, args: Dict[str, Any], session: SessionData) -> Dict[str, Any]:
    if tool_name == "list_images":
        images = session.list_images()
        return {
            "total_count": len(images),
            "images": images,
            "image_revision": session.image_revision,
        }

    elif tool_name == "get_image":
        filename = args.get("filename", "").strip()
        data = session.get_image(filename)
        if not data:
            available = [img["filename"] for img in session.list_images()]
            raise ValueError(f"Изображение «{filename}» не найдено в сессии. Доступные: {available}")
        mime, _ = mimetypes.guess_type(filename)
        mime = mime or "image/png"
        b64 = base64.b64encode(data).decode("ascii")
        return {
            "__mcp_content__": [
                {
                    "type": "image",
                    "data": b64,
                    "mimeType": mime
                },
                {
                    "type": "text",
                    "text": f"Изображение «{filename}» успешно получено ({round(len(data) / 1024, 1)} КБ, {mime}). Модель может визуально анализировать его содержимое."
                }
            ]
        }

    elif tool_name == "get_images":
        filenames = args.get("filenames")
        if not isinstance(filenames, list) or not 1 <= len(filenames) <= 16:
            raise ValueError("Ожидается от 1 до 16 имён изображений")

        safe_names = []
        seen = set()
        for filename in filenames:
            if not isinstance(filename, str) or not filename.strip():
                raise ValueError("Каждое имя изображения должно быть непустой строкой")
            safe_name = SessionData.sanitize_filename(filename)
            if safe_name not in seen:
                seen.add(safe_name)
                safe_names.append(safe_name)

        content = []
        for filename in safe_names:
            data = session.get_image(filename)
            if not data:
                raise ValueError(f"Изображение «{filename}» не найдено в сессии")
            mime, _ = mimetypes.guess_type(filename)
            content.append({
                "type": "image",
                "data": base64.b64encode(data).decode("ascii"),
                "mimeType": mime or "image/png",
            })
        content.append({
            "type": "text",
            "text": f"Пакетно получено изображений: {len(safe_names)}. Повторно их не запрашивай без конкретной причины.",
        })
        return {"__mcp_content__": content}

    elif tool_name == "upload_image":
        filename = args.get("filename", "").strip()
        b64_data = args.get("base64_data", "").strip()
        caption = args.get("caption", "").strip()
        insert_into_report = args.get("insert_into_report", False)

        if args.get("expected_revision") != session.revision:
            raise ValueError("Документ изменился: перечитайте get_report_state перед загрузкой рисунка")
        if not filename or not b64_data:
            raise ValueError("Не указан filename или base64_data")

        raw_bytes = _decode_image_data(b64_data, filename)
        safe_name = session.add_image(filename, raw_bytes)

        await session.broadcast({
            "type": "image_added",
            "source": "mcp_agent",
            "filename": safe_name,
            "size": len(raw_bytes),
            "url": f"/api/session/{session.token}/images/{safe_name}",
            "caption": caption,
            "image_revision": session.image_revision,
            "timestamp": time.time()
        })

        inserted = False
        if insert_into_report:
            md_caption = (caption or "Иллюстрация").replace("\n", " ").replace("]", "")
            img_md = f"\n\n![{md_caption}]({safe_name})\n"
            new_content = session.content.rstrip() + img_md
            await session_manager.update_content(
                token=session.token,
                content=new_content,
                source="mcp_agent"
            )
            inserted = True

        return {
            "status": "success",
            "filename": safe_name,
            "size_bytes": len(raw_bytes),
            "inserted_into_report": inserted,
            "revision": session.revision,
            "image_revision": session.image_revision,
            "message": f"Изображение «{safe_name}» сохранено и передано в браузер студента"
        }

    elif tool_name == "upload_images":
        if args.get("expected_revision") != session.revision:
            raise ValueError("Документ изменился: перечитайте outline перед пакетной загрузкой")
        items = args.get("images")
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_IMAGES_COUNT:
            raise ValueError(f"Ожидается от 1 до {MAX_IMAGES_COUNT} изображений")
        if len(session.images) + len(items) > MAX_IMAGES_COUNT:
            raise ValueError("Превышено допустимое количество изображений в сессии")
        anchors = {block.id: block.end for block in blocks(session.content, session.revision)}
        staged = []
        names = set(session.images)
        insertions: Dict[int, List[str]] = {}
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("filename"), str) or not isinstance(item.get("base64_data"), str):
                raise ValueError("Каждое изображение требует filename и base64_data")
            name = SessionData.sanitize_filename(item["filename"])
            if name in names:
                raise ValueError(f"Повторяющееся имя изображения: {name}")
            names.add(name)
            raw = _decode_image_data(item["base64_data"], name)
            staged.append((name, raw))
            anchor_id = item.get("after_block_id")
            if anchor_id is not None:
                if anchor_id not in anchors:
                    raise ValueError("Целевой блок для рисунка не найден в текущем outline")
                caption = str(item.get("caption") or "Иллюстрация").replace("\n", " ").replace("]", "")
                insertions.setdefault(anchors[anchor_id], []).append(f"![{caption}]({name})")
        new_md = session.content
        for offset, figures in sorted(insertions.items(), reverse=True):
            left, right = new_md[:offset].rstrip("\n"), new_md[offset:].lstrip("\n")
            new_md = left + ("\n\n" if left else "") + "\n\n".join(figures) + ("\n\n" if right else "\n") + right
        if [s.heading for s in sections(new_md)] != [s.heading for s in sections(session.content)]:
            raise ValueError("Вставка рисунков изменила структуру разделов")
        for name, raw in staged:
            session.add_image(name, raw)
        if new_md != session.content:
            await session_manager.update_content(session.token, new_md, source="mcp_agent")
        for name, raw in staged:
            await session.broadcast({"type": "image_added", "source": "mcp_agent", "filename": name,
                                     "size": len(raw), "url": f"/api/session/{session.token}/images/{name}",
                                     "image_revision": session.image_revision,
                                     "timestamp": time.time()})
        return {"status": "success", "uploaded_count": len(staged), "revision": session.revision,
                "image_revision": session.image_revision,
                "filenames": [name for name, _ in staged]}

    elif tool_name == "get_report_state":
        return {
            "token": session.token,
            "markdown_content": session.content,
            "revision": session.revision,
            "meta_revision": session.meta_revision,
            "image_revision": session.image_revision,
            "headings": [s.heading for s in sections(session.content)],
            "metadata": session.meta,
            "last_active": session.last_active
        }

    elif tool_name == "get_document_outline":
        rev = session.revision
        return {
            "revision": rev,
            "sections": [{
                "id": section_identifier(rev, section.start),
                "heading": section.heading, "level": section.level,
                "start_line": session.content.count("\n", 0, section.start) + 1,
            } for section in sections(session.content)],
            "blocks": [block.__dict__ for block in blocks(session.content, rev)],
        }

    elif tool_name in ("replace_block", "delete_block"):
        before = session.content
        if args.get("expected_revision") != session.revision:
            raise ValueError("Документ изменился: перечитайте outline перед точечной правкой")
        replacement = args.get("content") if tool_name == "replace_block" else None
        if tool_name == "replace_block" and not isinstance(replacement, str):
            raise ValueError("Поле content должно быть строкой")
        new_md = edit_block(before, session.revision, args.get("block_id", ""), replacement)
        if new_md != before:
            await session_manager.update_content(session.token, new_md, source="mcp_agent")
        return {
            "status": "updated" if new_md != before else "unchanged",
            "revision": session.revision,
            "diff": session.edit_history[-1]["diff"] if new_md != before else "",
        }

    elif tool_name == "move_figure":
        if args.get("expected_revision") != session.revision:
            raise ValueError("Документ изменился: перечитайте outline перед перемещением")
        new_md = move_figure(session.content, session.revision, args.get("block_id", ""),
                             args.get("before_block_id", ""))
        if new_md != session.content:
            await session_manager.update_content(session.token, new_md, source="mcp_agent")
            return {"status": "moved", "revision": session.revision, "diff": session.edit_history[-1]["diff"]}
        return {"status": "unchanged", "revision": session.revision, "diff": ""}

    elif tool_name == "get_last_edit":
        if not session.edit_history:
            return {"status": "empty"}
        entry = session.edit_history[-1]
        return {k: v for k, v in entry.items() if k != "before_content"} | {"is_current": session.revision == entry["after_revision"]}

    elif tool_name == "get_edit_history":
        return {"edits": [
            {k: v for k, v in entry.items() if k not in ("before_content", "diff")}
            for entry in reversed(session.edit_history)
        ]}

    elif tool_name == "rollback_last_edit":
        if not session.edit_history:
            raise ValueError("Нет правок для отката")
        entry = session.edit_history[-1]
        if entry["source"] != "mcp_agent":
            raise ValueError("Последняя правка сделана в браузере; агент не может её откатить")
        if args.get("expected_revision") != session.revision or entry["after_revision"] != session.revision:
            raise ValueError("После последней правки документ изменился; прочитайте новое состояние перед откатом")
        await session_manager.update_content(session.token, entry["before_content"], source="mcp_agent")
        return {"status": "rolled_back", "revision": session.revision,
                "diff": session.edit_history[-1]["diff"]}

    elif tool_name == "append_or_update_section":
        heading = args.get("section_heading", "").strip()
        content = args.get("section_content", "").strip()
        mode = args.get("mode", "update_or_append")
        before = session.content
        revision = hashlib.sha256(before.encode("utf-8")).hexdigest()
        expected = args.get("expected_revision")
        if expected != revision:
            raise ValueError("Документ изменился после get_report_state; загрузите его заново перед правкой")
        new_md, status = edit_section(before, heading, content, mode, args.get("section_id"), revision)
        before_headings = [s.heading for s in sections(before)]
        after_headings = [s.heading for s in sections(new_md)]
        if new_md == before:
            return {"status": "unchanged", "full_length": len(before), "revision": revision,
                    "headings_before": before_headings, "headings_after": after_headings, "diff": ""}
        diff = "".join(difflib.unified_diff(before.splitlines(keepends=True), new_md.splitlines(keepends=True),
                                             fromfile="до", tofile="после"))
        # Build and validate before the single state write.
        await session_manager.update_content(
            token=session.token,
            content=new_md,
            source="mcp_agent",
            section_name=heading
        )

        return {
            "status": status,
            "message": f"Раздел «{heading}» успешно обновлен в браузере пользователя",
            "full_length": len(new_md),
            "revision": hashlib.sha256(new_md.encode("utf-8")).hexdigest(),
            "headings_before": before_headings,
            "headings_after": after_headings,
            "diff": diff
        }

    elif tool_name == "patch_text":
        find = args.get("find", "")
        replacement = args.get("replace", "")
        before = session.content
        revision = hashlib.sha256(before.encode("utf-8")).hexdigest()
        if not find:
            raise ValueError("Не указан find")
        if args.get("expected_revision") != revision:
            raise ValueError("Документ изменился после get_report_state; загрузите его заново перед правкой")
        occurrences = before.count(find)
        if occurrences != 1:
            raise ValueError(f"Фрагмент должен встречаться ровно один раз, найдено: {occurrences}")
        new_md = before.replace(find, replacement, 1)
        if new_md == before:
            return {"status": "unchanged", "replacements": 0, "revision": revision, "diff": ""}
        diff = "".join(difflib.unified_diff(before.splitlines(keepends=True), new_md.splitlines(keepends=True),
                                             fromfile="до", tofile="после"))
        await session_manager.update_content(token=session.token, content=new_md, source="mcp_agent")
        return {
            "status": "updated", "replacements": 1,
            "revision": hashlib.sha256(new_md.encode("utf-8")).hexdigest(), "diff": diff,
        }

    elif tool_name == "apply_patches":
        before = session.content
        if args.get("expected_revision") != session.revision:
            raise ValueError("Документ изменился: перечитайте get_report_state перед пакетной правкой")
        patches = args.get("patches")
        if not isinstance(patches, list) or not 1 <= len(patches) <= 100:
            raise ValueError("Ожидается от 1 до 100 текстовых замен")
        spans = []
        for patch in patches:
            if (not isinstance(patch, dict) or not isinstance(patch.get("find"), str)
                    or not patch["find"] or not isinstance(patch.get("replace"), str)):
                raise ValueError("Каждая замена должна содержать непустой find и строку replace")
            find = patch["find"]
            if before.count(find) != 1:
                raise ValueError(f"Фрагмент «{find[:60]}» должен встречаться ровно один раз")
            start = before.index(find)
            spans.append((start, start + len(find), patch["replace"]))
        spans.sort()
        if any(spans[i][0] < spans[i - 1][1] for i in range(1, len(spans))):
            raise ValueError("Пакетные замены пересекаются")
        new_md = before
        for start, end, value in reversed(spans):
            new_md = new_md[:start] + value + new_md[end:]
        if [s.heading for s in sections(before)] != [s.heading for s in sections(new_md)]:
            raise ValueError("Правка меняет структуру заголовков; используйте инструменты разделов")
        if new_md == before:
            return {"status": "unchanged", "replacements": 0, "revision": session.revision, "diff": ""}
        await session_manager.update_content(session.token, new_md, source="mcp_agent")
        return {"status": "updated", "replacements": len(spans),
                "revision": session.revision, "diff": session.edit_history[-1]["diff"]}

    elif tool_name == "update_meta":
        expected_meta = args.get("expected_meta_revision")
        if expected_meta != session.meta_revision:
            raise ValueError("Реквизиты изменились: перечитайте get_report_state перед правкой")
        allowed = (
            "work_theme", "work_number", "work_type", "discipline", "institute",
            "department", "university", "ministry", "city", "year",
            "teachers", "students", "references", "custom_instructions"
        )
        patch = {k: v for k, v in args.items() if k in allowed}
        if not patch:
            raise ValueError("Не передано ни одного обновляемого поля")
        merged = {**(session.meta or {}), **patch}
        # Validate final metadata to protect title-page generation.
        # Validate references separately and omit malformed entries.
        refs = merged.get("references")
        if isinstance(refs, list):
            merged["references"] = [r for r in refs if isinstance(r, dict)]
        ReportMetadata(**merged)
        changed = merged != session.meta
        await session_manager.update_meta(
            token=session.token,
            meta=merged,
            source="mcp_agent"
        )
        return {
            "status": "success" if changed else "unchanged",
            "message": f"Реквизиты обновлены: {', '.join(patch.keys())}" if changed else "Реквизиты не изменились",
            "metadata": merged,
            "meta_revision": session.meta_revision,
        }

    elif tool_name == "import_profile":
        if args.get("expected_meta_revision") != session.meta_revision:
            raise ValueError("Реквизиты изменились: перечитайте get_report_state перед импортом профиля")
        profile = load_profile_input(args)
        merged = profile_metadata(profile, session.meta)
        await session_manager.update_meta(
            token=session.token,
            meta=merged,
            source="mcp_agent",
        )
        return {
            "status": "success",
            "message": "Профиль дисциплины и реквизиты титульного листа импортированы",
            "metadata": merged,
            "subject": profile["subject"],
            "meta_revision": session.meta_revision,
        }

    elif tool_name == "update_image_layout":
        filename = args.get("filename", "")
        if filename not in session.images:
            raise ValueError("Рисунок не прикреплён к отчёту")
        if args.get("expected_meta_revision") != session.meta_revision:
            raise ValueError("Реквизиты отчёта изменились; перечитайте get_report_state")
        fields = ("width_percent", "max_height_mm", "align", "keep_caption_with_image", "page_break_before")
        patch = {key: args[key] for key in fields if key in args}
        if not patch:
            raise ValueError("Не указаны параметры размещения")
        layouts = dict(session.meta.get("image_layouts") or {})
        current = layouts.get(filename, {})
        layout = ImageLayout(**{**current, **patch})
        layouts[filename] = layout.model_dump()
        merged = {**session.meta, "image_layouts": layouts}
        ReportMetadata(**merged)
        if merged != session.meta:
            await session_manager.update_meta(session.token, merged, source="mcp_agent")
        return {"status": "updated", "filename": filename, "layout": layouts[filename],
                "meta_revision": session.meta_revision}

    elif tool_name == "delete_image":
        filename = args.get("filename", "").strip()
        if not filename:
            raise ValueError("Не указан filename")
        if args.get("expected_revision") != session.revision:
            raise ValueError("Документ изменился: перечитайте get_report_state перед удалением рисунка")
        if args.get("expected_image_revision") != session.image_revision:
            raise ValueError("Набор изображений изменился: перечитайте list_images перед удалением рисунка")
        if any(image["filename"] == SessionData.sanitize_filename(filename) and image["is_in_report"]
               for image in session.list_images()):
            raise ValueError("Изображение используется в отчёте; сначала удалите ссылку из Markdown")
        removed = session.delete_image(filename)
        if removed:
            await session.broadcast({
                "type": "image_deleted",
                "source": "mcp_agent",
                "filename": SessionData.sanitize_filename(filename),
                "image_revision": session.image_revision,
                "timestamp": time.time()
            })
        return {
            "status": "deleted" if removed else "not_found",
            "filename": filename,
            "image_revision": session.image_revision,
        }

    elif tool_name == "delete_images":
        if args.get("expected_revision") != session.revision:
            raise ValueError("Документ изменился: перечитайте get_report_state перед удалением изображений")
        if args.get("expected_image_revision") != session.image_revision:
            raise ValueError("Набор изображений изменился: перечитайте list_images перед удалением изображений")
        filenames = args.get("filenames")
        if not isinstance(filenames, list) or not 1 <= len(filenames) <= MAX_IMAGES_COUNT:
            raise ValueError(f"Ожидается от 1 до {MAX_IMAGES_COUNT} имён изображений")

        safe_names = []
        seen = set()
        for filename in filenames:
            if not isinstance(filename, str) or not filename.strip():
                raise ValueError("Каждое имя изображения должно быть непустой строкой")
            safe_name = SessionData.sanitize_filename(filename)
            if safe_name not in seen:
                seen.add(safe_name)
                safe_names.append(safe_name)

        image_info = {image["filename"]: image for image in session.list_images()}
        blocked = [name for name in safe_names if image_info.get(name, {}).get("is_in_report")]
        if blocked:
            raise ValueError(f"Нельзя удалить изображения, используемые в отчёте: {blocked}")

        deleted = []
        for name in safe_names:
            if session.delete_image(name):
                deleted.append(name)
        for name in deleted:
            await session.broadcast({
                "type": "image_deleted",
                "source": "mcp_agent",
                "filename": name,
                "image_revision": session.image_revision,
                "timestamp": time.time()
            })
        return {"status": "deleted", "deleted": deleted, "image_revision": session.image_revision, "not_found": [
            name for name in safe_names if name not in deleted
        ]}

    elif tool_name == "lint_report":
        text_to_check = args.get("markdown_content") or session.content
        if not text_to_check.strip():
            return {"is_valid": False, "status": "invalid", "score": 0, "errors": [{"message": "Текст пуст"}], "warnings": []}

        meta_obj = ReportMetadata(**session.meta) if session.meta else ReportMetadata()
        docx_buffer = build_docx_report(
            meta=meta_obj,
            markdown_content=text_to_check,
            images_dict=session.images,
            options=GenerateOptions()
        )
        res = lint_docx_document(docx_buffer)
        list_stack: list[str] = []
        ordered_tasks = 0
        task_headings = 0
        tokens = MarkdownIt("commonmark").parse(text_to_check)
        for index, token in enumerate(tokens):
            if token.type in ("ordered_list_open", "bullet_list_open"):
                list_stack.append(token.type)
            elif token.type in ("ordered_list_close", "bullet_list_close"):
                if list_stack:
                    list_stack.pop()
            elif token.type == "list_item_open" and list_stack == ["ordered_list_open"]:
                ordered_tasks += 1
            elif token.type == "heading_open" and token.level == 0 and index + 1 < len(tokens):
                title = tokens[index + 1].content
                if re.match(r"^(?:\d+\.\s*)?задани[ея]\s*\d+", title, re.IGNORECASE):
                    task_headings += 1
        tasks_count = task_headings or ordered_tasks
        extra_warnings = [{
            "type": "UNUSED_IMAGE", "severity": "WARNING",
            "message": f"Прикреплённое изображение «{image['filename']}» не вставлено в отчёт.",
            "location": image["filename"],
            "fix_suggestion": "Вставьте ссылку на рисунок или удалите лишний файл",
        } for image in session.list_images(text_to_check) if not image["is_in_report"]]
        for name, actual in (("expected_task_count", tasks_count),
                             ("expected_figures_count", res.metrics.figures_count)):
            expected = args.get(name)
            if expected is None:
                continue
            if type(expected) is not int or expected < 0:
                raise ValueError(f"{name} должен быть неотрицательным целым числом")
            if expected != actual:
                subject = "заданий" if name == "expected_task_count" else "рисунков"
                extra_warnings.append({
                    "type": "COUNT_MISMATCH", "severity": "WARNING",
                    "message": f"Ожидалось {expected} {subject}, найдено {actual}.",
                    "location": "Структура отчёта",
                    "fix_suggestion": "Сверьте текст с методичкой и прикреплёнными файлами",
                })
        metrics = res.metrics.model_dump()
        metrics["tasks_count"] = tasks_count
        metrics["attached_images_count"] = len(session.images)
        return {
            "is_valid": res.is_valid,
            "status": "needs_review" if extra_warnings and res.status == "ready" else res.status,
            "score": max(0, res.score - 4 * len(extra_warnings)),
            "errors": [e.model_dump() for e in res.errors],
            "warnings": [w.model_dump() for w in res.warnings] + extra_warnings,
            "metrics": metrics
        }

    elif tool_name == "autofix_typography":
        if args.get("expected_revision") != session.revision:
            raise ValueError("Документ изменился: перечитайте get_report_state перед автоисправлением")
        content = session.content
        lines = content.split("\n")
        fixed_lines = []
        fixes_count = 0
        protected_lines = set()
        for token in MarkdownIt("commonmark").parse(content):
            if not token.map:
                continue
            if token.type in ("fence", "code_block", "html_block") or (
                token.type == "inline" and any(
                    child.type in ("link_open", "image", "html_inline")
                    for child in (token.children or [])
                )
            ):
                protected_lines.update(range(*token.map))

        for index, line in enumerate(lines):
            if index in protected_lines or re.match(r"^\s{0,3}\[[^\]]+\]:", line):
                fixed_lines.append(line)
                continue
            if re.match(r"^#{1,6}\s+", line):
                cl = strip_trailing_dot(line)
                if cl != line:
                    fixes_count += 1
                fixed_lines.append(cl)
                continue

            typographed = apply_typography_outside_code(line)
            if typographed != line:
                fixes_count += 1
            fixed_lines.append(typographed)

        new_text = "\n".join(fixed_lines)
        if new_text != content:
            await session_manager.update_content(session.token, new_text, source="mcp_agent")
        return {
            "status": "success",
            "fixes_applied_count": fixes_count,
            "revision": session.revision,
            "diff": session.edit_history[-1]["diff"] if new_text != content else "",
            "message": "Типографика отчета приведена к ГОСТ 7.32 и обновлена в браузере"
        }

    else:
        raise ValueError(f"Неизвестный инструмент: {tool_name}")


async def _dispatch_mcp_tool_safely(
    tool_name: str,
    args: Dict[str, Any],
    session: SessionData,
) -> Dict[str, Any]:
    """Allow parallel reads while serializing revision-sensitive mutations."""
    if tool_name in MCP_MUTATING_TOOLS:
        async with session.mcp_write_lock:
            return await _dispatch_mcp_tool(tool_name, args, session)
    return await _dispatch_mcp_tool(tool_name, args, session)


# ==============================================================================
# Browser synchronization endpoints (Session API).
# ==============================================================================

@router.get("/api/session/init")
async def init_session(token: Optional[str] = Query(None)):
    """Initialize or restore a browser session."""
    session = session_manager.get_or_create(token)
    return {
        "token": session.token,
        "content": session.content,
        "revision": session.revision,
        "meta_revision": session.meta_revision,
        "image_revision": session.image_revision,
        "meta": session.meta,
        "images": session.list_images(),
        "deleted": sorted(session.deleted_images)
    }


@router.post("/api/session/{token}/images")
async def upload_session_images(
    token: str,
    files: List[UploadFile] = File(...),
    restoring: bool = Query(False),
    client_id: Optional[str] = Query(None),
):
    """Upload browser images into the session."""
    session = session_manager.get_or_create(token)
    if not 1 <= len(files) <= MAX_IMAGES_COUNT or len(session.images) + len(files) > MAX_IMAGES_COUNT:
        raise HTTPException(status_code=400, detail="Превышено допустимое число изображений")
    staged = []
    names = set(session.images)
    for file in files:
        name = SessionData.sanitize_filename(file.filename or "image.png")
        data = await file.read(MAX_IMAGE_SIZE + 1)
        if restoring and name in session.deleted_images:
            raise HTTPException(status_code=409, detail=f"Изображение «{name}» было удалено из живой сессии")
        if name in names or not data or len(data) > MAX_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail=f"Недопустимый или повторяющийся файл: {name}")
        names.add(name)
        staged.append((name, data))

    uploaded = []
    for name, data in staged:
        session.add_image(name, data)
        uploaded.append({"filename": name, "size_bytes": len(data),
                         "url": f"/api/session/{token}/images/{name}"})
    for item in uploaded:
        item["image_revision"] = session.image_revision
    for name, data in staged:
        await session.broadcast({
            "type": "image_added", "source": "web", "filename": name,
            "size": len(data), "url": f"/api/session/{token}/images/{name}",
            "client_id": client_id, "image_revision": session.image_revision,
            "timestamp": time.time()
        })
    return {"uploaded": uploaded}


@router.get("/api/session/{token}/images")
async def get_session_images(token: str):
    """List all session images."""
    session = session_manager.get_or_create(token)
    return {
        "images": session.list_images(),
        "deleted": sorted(session.deleted_images),
        "image_revision": session.image_revision,
    }


@router.get("/api/session/{token}/images/{filename}")
async def serve_session_image(token: str, filename: str):
    """Serve image bytes for preview and download."""
    session = session_manager.get_or_create(token)
    data = session.get_image(filename)
    if not data:
        raise HTTPException(status_code=404, detail="Изображение не найдено")
    mime, _ = mimetypes.guess_type(filename)
    return Response(content=data, media_type=mime or "image/png")


@router.delete("/api/session/{token}/images/{filename}")
async def delete_session_image(
    token: str,
    filename: str,
    client_id: Optional[str] = Query(None),
    expected_image_revision: Optional[str] = Query(None),
):
    """Delete an image from the session."""
    session = session_manager.get_or_create(token)
    if expected_image_revision is not None and expected_image_revision != session.image_revision:
        raise HTTPException(status_code=409, detail="Набор изображений изменился, обновите manifest")
    success = session.delete_image(filename)
    if success:
        await session.broadcast({
            "type": "image_deleted",
            "source": "web",
            "filename": filename,
            "client_id": client_id,
            "image_revision": session.image_revision,
            "timestamp": time.time()
        })
    return {
        "status": "deleted" if success else "not_found",
        "filename": filename,
        "image_revision": session.image_revision,
    }



@router.post("/api/session/{token}/sync")
async def sync_session(token: str, payload: dict = Body(...)):
    """Accept browser updates from manual report editing."""
    session = session_manager.get_or_create(token)
    has_content = "content" in payload
    has_content_patches = "content_patches" in payload
    if has_content and has_content_patches:
        raise HTTPException(status_code=422, detail="Передавайте content или content_patches, но не оба поля")

    next_content = None
    # Check both revisions before writing so a conflict cannot partially
    # update the request's text or metadata.
    if has_content_patches:
        expected = payload.get("expected_revision")
        if expected is None:
            raise HTTPException(status_code=422, detail="content_patches требует expected_revision")
        if expected != session.revision:
            return Response(
                content=json.dumps({"status": "conflict", "conflict_type": "content",
                                    "content": session.content, "revision": session.revision}, ensure_ascii=False),
                status_code=409, media_type="application/json",
            )
        next_content = _apply_content_patches(session.content, payload["content_patches"])
    elif has_content:
        if not isinstance(payload["content"], str):
            raise HTTPException(status_code=422, detail="content должен быть строкой")
        next_content = payload["content"]
        expected = payload.get("expected_revision")
        if expected is not None and expected != session.revision and payload["content"] != session.content:
            return Response(
                content=json.dumps({"status": "conflict", "conflict_type": "content",
                                    "content": session.content, "revision": session.revision}, ensure_ascii=False),
                status_code=409, media_type="application/json",
            )
    if "meta" in payload:
        if not isinstance(payload["meta"], dict):
            raise HTTPException(status_code=422, detail="meta должен быть объектом")
        expected_meta = payload.get("expected_meta_revision")
        if expected_meta is not None and expected_meta != session.meta_revision and payload["meta"] != session.meta:
            return Response(
                content=json.dumps({"status": "conflict", "conflict_type": "meta",
                                    "meta": session.meta, "meta_revision": session.meta_revision}, ensure_ascii=False),
                status_code=409, media_type="application/json",
            )
    if next_content is not None and next_content != session.content:
        await session_manager.update_content(
            token, next_content, source="web", client_id=payload.get("client_id")
        )
    if "meta" in payload and payload["meta"] != session.meta:
        await session_manager.update_meta(
            token, payload["meta"], source="web", client_id=payload.get("client_id")
        )
    session.touch()
    return {"status": "ok", "token": token, "revision": session.revision,
            "meta_revision": session.meta_revision}


@router.get("/api/session/{token}/events")
async def session_events_sse(token: str, request: Request):
    """Push agent edits to the browser through Server-Sent Events."""
    session = session_manager.get_or_create(token)
    queue: asyncio.Queue = asyncio.Queue()
    session.add_listener(queue)

    async def event_generator():
        try:
            # Confirm the connection with a welcome event.
            yield f"event: connected\ndata: {json.dumps({'token': token})}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: sync\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # Keep the connection alive.
                    yield ": ping\n\n"
        finally:
            session.remove_listener(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ==============================================================================
# Endpoints: MCP Server over SSE (Model Context Protocol HTTP Transport)
# ==============================================================================

@router.get("/api/mcp/sse")
async def mcp_sse_transport(request: Request, token: str = Query(...)):
    """Connect MCP clients through SSE using a session token.

    Example: https://example.com/api/mcp/sse?token=tok_...
    """
    session = session_manager.get(token)
    if not session:
        session = session_manager.get_or_create(token)

    conn_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _mcp_connections[conn_id] = queue

    # Honor reverse-proxy proto/host/prefix headers so the POST endpoint
    # shares the client's connection origin, as required by the MCP SDK.
    raw_proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    proto = raw_proto.split(",")[0].strip().lower()

    raw_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    host = raw_host.split(",")[0].strip()

    raw_prefix = request.headers.get("x-forwarded-prefix") or request.scope.get("root_path", "")
    root_path = raw_prefix.strip().rstrip("/")
    if root_path and not root_path.startswith("/"):
        root_path = f"/{root_path}"

    endpoint_url = f"{proto}://{host}{root_path}/api/mcp/messages?token={session.token}&sessionId={conn_id}"

    async def mcp_stream():
        try:
            # MCP handshake: advertise the JSON-RPC message endpoint URL.
            yield f"event: endpoint\ndata: {endpoint_url}\n\n"
            await asyncio.sleep(0.001)

            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            _mcp_connections.pop(conn_id, None)

    return StreamingResponse(
        mcp_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/api/mcp/messages")
async def mcp_post_message(
    request: Request,
    token: str = Query(...),
    sessionId: Optional[str] = Query(None)
):
    """Accept JSON-RPC 2.0 commands from a connected MCP agent."""
    session = session_manager.get_or_create(token)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Невалидный JSON")

    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})

    response_payload = None

    if method == "initialize":
        response_payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "prompts": {},
                    "resources": {}
                },
                "serverInfo": {
                    "name": "report-engine-live",
                    "version": APP_VERSION,
                    "sessionToken": session.token
                },
                "instructions": (
                    "Сервер Report Engine (ГОСТ 7.32-2017, ГОСТ 2.105-2019).\n"
                    "Сначала прочитай канонические правила в ресурсе report://rules/gost732. "
                    "Для нового отчёта собери черновик локально и используй пакетные операции; "
                    "для существующего отчёта применяй точечные правки. После записи используй "
                    "возвращённые revision, meta_revision и image_revision. "
                    "tools/list может возвращать nextCursor — прочитай все страницы discovery. "
                    "Для переноса настроек используй import_profile с объектом report-engine-profile "
                    "версии 1 и свежей meta_revision. "
                    "Независимые чтения можно отправлять отдельными параллельными вызовами, "
                    "но записи с ревизиями выполняй последовательно. "
                    "Не выдумывай факты и не сохраняй дополнительные skills без отдельной просьбы пользователя. "
                    "Токен сессии протухает — при обрыве попроси свежий URL."
                )
            }
        }

    elif method == "notifications/initialized":
        return Response(status_code=202)

    elif method == "ping":
        response_payload = {"jsonrpc": "2.0", "id": req_id, "result": {}}

    elif method == "prompts/list":
        response_payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "prompts": [
                    {
                        "name": "write_report",
                        "description": "Написать или оформить отчёт (лабораторная, практическая, курсовая работа, проект, практика) прямо в открытом браузере",
                        "arguments": [
                            {"name": "task", "description": "Тема или задание работы", "required": False}
                        ]
                    }
                ]
            }
        }

    elif method == "prompts/get":
        prompt_name = params.get("name")
        task_text = params.get("arguments", {}).get("task", "")
        prompt_body = _load_skill_text() or (
            "Ты — инженерный ассистент студента. Веди отчёт через get_report_state, "
            "append_or_update_section и lint_report в безличном стиле."
        )
        if task_text:
            prompt_body += f"\nЗадание пользователя: {task_text}"

        response_payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "description": "Оформление отчёта по ГОСТ 7.32",
                "messages": [
                    {
                        "role": "user",
                        "content": {"type": "text", "text": prompt_body}
                    }
                ]
            }
        }

    elif method == "resources/list":
        resources_list = [
            {
                "uri": f"report://document/{session.token}",
                "name": "Текущий текст отчёта",
                "description": "Актуальный Markdown-текст из открытой вкладки браузера",
                "mimeType": "text/markdown"
            },
            {
                "uri": "report://rules/gost732",
                "name": "Инструкция агента (SKILL.md)",
                "description": "Полные правила ведения отчёта: порядок работы, стиль, рисунки, формулы, таблицы",
                "mimeType": "text/markdown"
            }
        ]
        for img in session.list_images():
            resources_list.append({
                "uri": f"report://image/{session.token}/{img['filename']}",
                "name": f"Изображение: {img['filename']}",
                "description": f"Иллюстрация к работе ({img['size_kb']} КБ)",
                "mimeType": img["mime_type"]
            })

        response_payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "resources": resources_list
            }
        }

    elif method == "resources/read":
        uri = params.get("uri", "")
        if (
            uri.startswith(f"report://image/{session.token}/")
            or uri.startswith(f"report://image/{token}/")
        ):
            filename = uri.split("/")[-1]
            data = session.get_image(filename)
            if data:
                mime, _ = mimetypes.guess_type(filename)
                b64 = base64.b64encode(data).decode("ascii")
                response_payload = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "contents": [
                            {"uri": uri, "mimeType": mime or "image/png", "blob": b64}
                        ]
                    }
                }
            else:
                response_payload = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": f"Image {filename} not found"}
                }
        elif "rules/gost732" in uri:
            content_text = _load_skill_text() or "# Требования ГОСТ 7.32-2017\n- Безличная форма."
            response_payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "contents": [
                        {"uri": uri, "mimeType": "text/markdown", "text": content_text}
                    ]
                }
            }
        else:
            content_text = session.content
            response_payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "contents": [
                        {"uri": uri, "mimeType": "text/markdown", "text": content_text}
                    ]
                }
            }

    elif method == "tools/list":
        try:
            tools_result = _mcp_tools_page(params.get("cursor"))
            response_payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": tools_result,
            }
        except ValueError as exc:
            response_payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": str(exc)},
            }

    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        try:
            result_data = await _dispatch_mcp_tool_safely(tool_name, tool_args, session)
            if isinstance(result_data, dict) and "__mcp_content__" in result_data:
                content_payload = result_data["__mcp_content__"]
            else:
                content_payload = [
                    {"type": "text", "text": json.dumps(result_data, ensure_ascii=False, indent=2)}
                ]
            response_payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": content_payload,
                    "isError": False
                }
            }
        except Exception as e:
            response_payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": f"Ошибка выполнения {tool_name}: {str(e)}"}
                    ],
                    "isError": True
                }
            }
    else:
        if req_id is not None:
            response_payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method '{method}' not found"}
            }

    # Send the response through the active SSE connection for this sessionId.
    if sessionId and sessionId in _mcp_connections and response_payload:
        await _mcp_connections[sessionId].put(response_payload)
        return Response(status_code=202)

    return response_payload or Response(status_code=202)
