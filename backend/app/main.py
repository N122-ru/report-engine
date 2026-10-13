"""
Report Engine - FastAPI Application
"""

import json
import re
import os
import io
import zipfile
import docx.opc.exceptions
from urllib.parse import quote
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

from .models.report import ReportMetadata, GenerateOptions
from .models.linter import LinterResult
from .engine.generator import build_docx_report
from .engine.linter import lint_docx_document
from .engine.pdf_converter import convert_docx_to_pdf, pdf_export_status
from .engine.typography import apply_typography_outside_code
from .engine.update_checker import get_update_info
from .version import APP_VERSION
from .engine.security import (
    check_rate_limit,
    PDF_SEMAPHORE,
    MAX_MARKDOWN_SIZE,
    MAX_AUTOFIX_SIZE,
    MAX_IMAGE_SIZE,
    MAX_IMAGES_COUNT,
    MAX_VERIFY_SIZE
)

from .engine.mcp_router import router as mcp_router

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

app = FastAPI(
    title="Report Engine API",
    description="Web-генератор и верификатор отчетов по ГОСТ 7.32 и ГОСТ 2.105",
    version=APP_VERSION
)

# Support reverse-proxy headers (X-Forwarded-Proto, X-Forwarded-Host).
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Register session and remote MCP routes.
app.include_router(mcp_router)

# Apply security headers and SPA cache policy: never cache index.html,
# which would pin stale bundles; cache Vite's hashed assets as immutable.
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "Report Engine",
        "version": APP_VERSION,
    }


@app.get("/api/capabilities")
def capabilities():
    """Expose optional runtime capabilities such as PDF conversion."""
    return pdf_export_status()


@app.get("/api/version")
def version_info():
    """Expose the running version and the optional release update status."""
    return {
        "version": APP_VERSION,
        "update": get_update_info(),
    }

@app.post("/api/generate")
async def generate_report(
    request: Request,
    meta: str = Form(..., description="JSON-строка с метаданными ReportMetadata"),
    content: str = Form("", description="Сырой Markdown отчета"),
    format: str = Form("docx", description="Формат вывода: docx или pdf"),
    options: Optional[str] = Form(None, description="Опции GenerateOptions в формате JSON"),
    images: List[UploadFile] = File(default=[])
):
    """Generate and download a report formatted according to GOST 7.32."""
    await check_rate_limit(request, max_requests=30, window_seconds=60)

    if len(content.encode("utf-8")) > MAX_MARKDOWN_SIZE:
        raise HTTPException(status_code=413, detail="Размер текста отчета превышает допустимый лимит (500 КБ)")

    if len(images) > MAX_IMAGES_COUNT:
        raise HTTPException(status_code=400, detail=f"Превышено максимальное количество иллюстраций ({MAX_IMAGES_COUNT})")

    try:
        meta_dict = json.loads(meta)
        meta_obj = ReportMetadata(**meta_dict)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Ошибка разбора метаданных: {str(e)}")

    opt_obj = GenerateOptions()
    if options:
        try:
            opt_dict = json.loads(options)
            opt_obj = GenerateOptions(**opt_dict)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Ошибка разбора опций: {str(e)}")

    normalized_format = format.lower()
    if normalized_format not in ("docx", "pdf"):
        raise HTTPException(status_code=400, detail="Формат должен быть docx или pdf")
    if normalized_format == "pdf" and not pdf_export_status()["pdf_export"]:
        raise HTTPException(
            status_code=501,
            detail="PDF недоступен: установите офисный CLI-конвертер или экспортируйте DOCX вручную",
        )

    images_dict = {}
    for img in images:
        if img.filename:
            content_bytes = await img.read(MAX_IMAGE_SIZE + 1)
            if len(content_bytes) > MAX_IMAGE_SIZE:
                raise HTTPException(status_code=413, detail=f"Размер файла «{img.filename}» превышает лимит 25 МБ")
            images_dict[img.filename] = content_bytes
            basename = os.path.basename(img.filename)
            images_dict[basename] = content_bytes

    try:
        docx_buffer = build_docx_report(
            meta=meta_obj,
            markdown_content=content,
            images_dict=images_dict,
            options=opt_obj
        )
        docx_bytes = docx_buffer.getvalue()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации DOCX: {str(e)}")

    safe_theme = re.sub(r'[\\/*?:"<>|]', "", meta_obj.work_theme).strip()
    filename_base = f"Отчет_ЛР{meta_obj.work_number}_{safe_theme[:25]}".strip()
    if not filename_base:
        filename_base = "Отчет"

    if normalized_format == "pdf":
        try:
            async with PDF_SEMAPHORE:
                pdf_buffer = convert_docx_to_pdf(docx_bytes)
            encoded_pdf_name = quote(f"{filename_base}.pdf")
            disposition = f"attachment; filename=\"report.pdf\"; filename*=UTF-8''{encoded_pdf_name}"
            return Response(
                content=pdf_buffer.getvalue(),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": disposition,
                    "Access-Control-Expose-Headers": "Content-Disposition"
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка конвертации в PDF: {str(e)}")

    encoded_docx_name = quote(f"{filename_base}.docx")
    disposition = f"attachment; filename=\"report.docx\"; filename*=UTF-8''{encoded_docx_name}"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": disposition,
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )

@app.post("/api/verify", response_model=LinterResult)
async def verify_docx(request: Request, file: UploadFile = File(...)):
    """Audit an uploaded DOCX and return errors, warnings, and a GOST score (0–100)."""
    await check_rate_limit(request, max_requests=30, window_seconds=60)

    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы формата .docx")

    content_bytes = await file.read(MAX_VERIFY_SIZE + 1)
    if len(content_bytes) > MAX_VERIFY_SIZE:
        raise HTTPException(status_code=413, detail="Размер файла превышает лимит 25 МБ")

    try:
        docx_buffer = io.BytesIO(content_bytes)
        result = lint_docx_document(docx_buffer)
        return result
    except (zipfile.BadZipFile, docx.opc.exceptions.PackageNotFoundError, KeyError) as e:
        raise HTTPException(status_code=400, detail=f"Поврежденный или невалидный файл DOCX: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка проверки документа: {str(e)}")

@app.post("/api/autofix")
async def autofix_markdown(request: Request, content: str = Form(...)):
    """Normalize Markdown typography without changing fenced code.

    Remove heading periods, normalize caption dashes and quotation marks,
    and collapse redundant blank lines.
    """
    await check_rate_limit(request, max_requests=45, window_seconds=60)

    if len(content.encode("utf-8")) > MAX_AUTOFIX_SIZE:
        raise HTTPException(status_code=413, detail="Размер текста для автоисправления превышает допустимый лимит (500 КБ)")

    def _strip_single_dot(s: str) -> str:
        """Remove a single trailing period while preserving ellipses."""
        if s.endswith(".") and not s.endswith(".."):
            return s[:-1]
        return s

    def _is_generic_caption_str(s: str) -> bool:
        s = s.strip().lower()
        if not s or s in ("image", "img", "рисунок", "рис", "рис.", "иллюстрация", "photo", "фото", "скриншот", "screenshot"):
            return True
        if re.search(r'\.(?:png|jpe?g|svg|webp|gif|bmp)$', s):
            return True
        if re.match(r'^(?:рисунок|рис\.?)?\s*\d+(?:\.\d+)*$', s):
            return True
        return False

    fixes = []

    # Deduplicate figure captions outside fenced code in a preliminary pass.
    def _dedup_captions_in_content(raw_text: str) -> str:
        code_chunks = re.split(r"(```[\s\S]*?```)", raw_text)
        out_chunks = []
        for chunk in code_chunks:
            if chunk.startswith("```"):
                out_chunks.append(chunk)
                continue

            # Consume a duplicate caption following the image.
            pat_after = re.compile(
                r'(!\[([^\]]*)\]\(([^)]+)\))\s*\n+((?:\*{1,2}|_{1,2})?\s*(?:рисунок|рис\.?)\s*(?:\d+(?:\.\d+)*)?(?:\s*[:–—-]\s*([^\n*_\r]+)|)(?:\*{1,2}|_{1,2})?)(?=\n|$)',
                flags=re.IGNORECASE
            )
            def _sub_after(m):
                full_img = m.group(1)
                alt = m.group(2).strip()
                src = m.group(3).strip()
                dup_line = m.group(4).strip()
                raw_title = m.group(5) or ""
                title = raw_title.strip().rstrip("*_").strip()
                fixes.append(f"Удалена дублирующая подпись рисунка: «{dup_line[:35]}»")
                if (_is_generic_caption_str(alt) or alt.lower() in title.lower()) and title:
                    return f"![{title}]({src})"
                return full_img

            chunk = pat_after.sub(_sub_after, chunk)

            # Consume a duplicate caption preceding the image.
            pat_before = re.compile(
                r'((?:\*{1,2}|_{1,2})?\s*(?:рисунок|рис\.?)\s*(?:\d+(?:\.\d+)*)?(?:\s*[:–—-]\s*([^\n*_\r]+)|)(?:\*{1,2}|_{1,2})?)\s*\n+(!\[([^\]]*)\]\(([^)]+)\))',
                flags=re.IGNORECASE
            )
            def _sub_before(m):
                dup_line = m.group(1).strip()
                raw_title = m.group(2) or ""
                title = raw_title.strip().rstrip("*_").strip()
                full_img = m.group(3)
                alt = m.group(4).strip()
                src = m.group(5).strip()
                fixes.append(f"Удалена подпись рисунка перед картинкой: «{dup_line[:35]}»")
                if (_is_generic_caption_str(alt) or alt.lower() in title.lower()) and title:
                    return f"![{title}]({src})"
                return full_img

            # Remove AI search markers and footnotes such as [cite: 4] and [^1^].
            pat_cite = re.compile(r'\[cite:\s*[^\]]+\]|\[citation:\s*[^\]]+\]|【\d+(?::\d+)?†source】|\[\^\d+\^\]', flags=re.IGNORECASE)
            if pat_cite.search(chunk):
                fixes.append("Удалены мусорные поисковые маркеры и сноски ИИ ([cite: ...])")
                chunk = pat_cite.sub("", chunk)
                chunk = re.sub(r'[ \t]+([.,;:!?])', r'\1', chunk)

            # Separate colon-ended lines from code literals to avoid justification gaps.
            pat_colon = re.compile(r'(:\s*)\n\s*(`[^`\n]+`|[0-9a-fA-F\-]{12,}|[01\-]{16,})\s*$', flags=re.MULTILINE)
            def _sub_colon(m):
                fixes.append("Устранено растяжение пробелов («дыры») перед литералом кода")
                return f"{m.group(1)}\n\n{m.group(2)}\n"
            chunk = pat_colon.sub(_sub_colon, chunk)

            # Convert standalone assignment headings into aim-section prose.
            pat_task = re.compile(r'^#+\s*(?:Задание на работу|Задание|Задачи (?:лабораторной|практической|курсовой)?\s*работы|Задачи работы)\s*$', flags=re.MULTILINE | re.IGNORECASE)
            if pat_task.search(chunk):
                fixes.append("Раздел «Задание» преобразован в связные задачи в разделе цели работы (ГОСТ 7.32)")
                chunk = pat_task.sub("Для достижения цели поставлены задачи:", chunk)

            # Simplify verbose interface-state phrasing.
            if re.search(r'находится в активном состоянии', chunk, flags=re.IGNORECASE):
                chunk = re.sub(r'находится в активном состоянии и обеспечивает', 'активен, обеспечивает', chunk, flags=re.IGNORECASE)
                chunk = re.sub(r'находится в активном состоянии', 'активен', chunk, flags=re.IGNORECASE)
                fixes.append("Упрощены формулировки состояния интерфейсов («находится в активном состоянии» -> «активен»)")

            out_chunks.append(chunk)
        return "".join(out_chunks)

    content = _dedup_captions_in_content(content)
    lines = content.split("\n")
    fixed_lines = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()
        new_line = line

        # Track fenced code so autofix never changes listing contents.
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            fixed_lines.append(new_line)
            continue

        if in_code_block:
            fixed_lines.append(new_line)
            continue

        # Remove trailing Markdown heading periods, allowing trailing whitespace.
        if stripped.startswith("#"):
            if re.search(r"(?<!\.)\.\s*$", line):
                new_line = re.sub(r"(?<!\.)\.\s*$", "", line)
                fixes.append(f"Удалена точка в заголовке: «{stripped[:30]}»")

        # Normalize figure-caption dashes and trailing periods.
        if stripped.startswith("!["):
            match = re.search(r"^!\[(.*?)\]\((.*?)\)$", stripped)
            if match:
                caption = _strip_single_dot(match.group(1))
                caption = re.sub(r"[ \t]+[-–][ \t]+", " — ", caption)
                url = match.group(2)
                new_line = f"![{caption}]({url})"
                if caption != match.group(1) or new_line != line:
                    fixes.append(f"Нормализована подпись иллюстрации: «{caption[:30]}»")

        # Normalize caption dashes with nonbreaking spacing immediately,
        # avoiding repeated fixes when the typography pass runs afterward.
        if re.search(r"(Рисунок|Таблица|Листинг)\s+\d+(?:\.\d+)*\s+[-–—]", new_line):
            before = new_line
            new_line = re.sub(r"((Рисунок|Таблица|Листинг)\s+\d+(?:\.\d+)*)\s+[-–—]\s*", "\\1 — ", new_line)
            new_line = _strip_single_dot(new_line.rstrip())
            if new_line != before:
                fixes.append("Заменен дефис на длинное тире в подписи")

        # Apply typography to prose or individual table cells, preserving
        # pipe delimiters and table separator rows.
        if not stripped.startswith("#") and not stripped.startswith("!["):
            if stripped.startswith("|"):
                if not re.fullmatch(r"[\s|:\-]+", stripped):
                    cells = re.split(r"(?<!\\)\|", new_line)
                    fixed_cells = [apply_typography_outside_code(c) if c.strip() else c for c in cells]
                    joined = "|".join(fixed_cells)
                    if joined != new_line:
                        fixes.append("Привязаны неразрывные пробелы в строке таблицы")
                        new_line = joined
            else:
                applied = apply_typography_outside_code(new_line)
                if applied != new_line:
                    fixes.append("Привязаны неразрывные пробелы и исправлены кавычки-«елочки»")
                    new_line = applied

        fixed_lines.append(new_line)

    # Collapse blank lines only outside fences; preserve code contents.
    result_parts: list = []
    chunk: list = []
    chunk_fenced = False
    for ln in fixed_lines:
        if ln.strip().startswith("```"):
            if chunk:
                seg = "\n".join(chunk)
                result_parts.append(seg if chunk_fenced else re.sub(r"\n{3,}", "\n\n", seg))
                chunk = []
            chunk_fenced = not chunk_fenced
            result_parts.append(ln)
        else:
            chunk.append(ln)
    if chunk:
        seg = "\n".join(chunk)
        result_parts.append(seg if chunk_fenced else re.sub(r"\n{3,}", "\n\n", seg))
    result_text = "\n".join(result_parts)

    return {
        "fixed_content": result_text,
        "fixes_applied": fixes
    }

# -------------------------------------------------------------
# Serve the built React/Vite SPA.
# -------------------------------------------------------------
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.exists(frontend_dist):
    assets_path = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        # Prevent path traversal: resolved paths must stay inside frontend_dist.
        safe_path = os.path.abspath(os.path.join(frontend_dist, full_path))
        no_store = {"Cache-Control": "no-store"}
        if not (safe_path == frontend_dist or safe_path.startswith(frontend_dist + os.sep)):
            return FileResponse(os.path.join(frontend_dist, "index.html"), headers=no_store)
        if os.path.exists(safe_path) and os.path.isfile(safe_path):
            if safe_path == os.path.join(frontend_dist, "index.html"):
                return FileResponse(safe_path, headers=no_store)
            return FileResponse(safe_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"), headers=no_store)
