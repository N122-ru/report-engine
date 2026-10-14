"""Standalone MCP server for local report-agent workflows."""

import argparse
import base64
import binascii
import json
import mimetypes
from pathlib import Path
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .engine.headless_report import HeadlessReport
from .engine.image_input import IMAGE_SOURCE_SCHEMA, MAX_IMAGES_COUNT, load_image_input
from .engine.mcp_batch import BATCH_SCHEMA, resolve_batch_arguments, validate_batch_calls
from .engine.pdf_converter import pdf_export_enabled
from .engine.profile import load_profile_input
from .engine.agent_resources import get_capabilities, read_agent_asset, read_reference, reference_resources
from .engine.report_safety import conflict_payload, is_conflict_message
from .version import APP_VERSION


SERVER_VERSION = APP_VERSION
SKILL_PATH = Path(__file__).resolve().parents[2] / "assets" / "SKILL.md"


def _skill_text() -> str:
    try:
        return read_agent_asset("SKILL.md")
    except (OSError, ValueError):
        return "# Report Engine\nСледуй правилам ГОСТ 7.32 и проверяй отчёт через lint_report."


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _text_result(value: Any, *, is_error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(text=value if isinstance(value, str) else _json(value))],
        structuredContent=value if isinstance(value, dict) else None,
        isError=is_error,
    )


def _string(args: dict[str, Any], name: str, *, required: bool = True) -> str:
    value = args.get(name)
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"Параметр «{name}» должен быть непустой строкой")
    return value


def _object(args: dict[str, Any], name: str, *, required: bool = True) -> dict[str, Any]:
    value = args.get(name)
    if value is None and not required:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Параметр «{name}» должен быть объектом")
    return value


def _decode_image(value: str) -> bytes:
    encoded = value.strip()
    if "," in encoded and "base64" in encoded[:64].lower():
        encoded = encoded.split(",", 1)[1]
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Параметр base64_data содержит невалидные данные") from exc


def _tool(
    name: str, description: str, properties: dict[str, Any],
    required: list[str] | None = None, **schema_fields: Any,
) -> types.Tool:
    return types.Tool(
        name=name,
        description=description,
        inputSchema={
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": True,
            **schema_fields,
        },
    )


def _tools() -> list[types.Tool]:
    revision = {"type": "string", "description": "Свежая версия из get_report_state"}
    tools = [
        types.Tool(
            name="batch",
            description="Выполнить от 1 до 20 инструментов последовательно; ошибки собираются без отката правок.",
            inputSchema=BATCH_SCHEMA,
        ),
        _tool(
            "create_report",
            "Создать один новый отчёт в оперативной памяти процесса.",
            {"metadata": {"type": "object", "description": "Реквизиты ReportMetadata"}},
        ),
        _tool(
            "import_profile",
            "Импортировать версионированный профиль дисциплины и титульного листа из JSON-объекта или локального файла. "
            "При первом вызове профиль создаёт отчёт в RAM; для существующего отчёта требуется свежая meta_revision.",
            {
                "profile": {"type": "object", "description": "Объект report-engine-profile версии 1"},
                "file_path": {"type": "string", "description": "Путь к JSON-файлу относительно текущего каталога"},
                "expected_meta_revision": revision,
            },
        ),
        _tool(
            "get_report_state",
            "Получить Markdown, реквизиты, изображения и три текущие версии отчёта.",
            {"detail": {"type": "string", "enum": ["full", "digest"], "default": "full"}},
        ),
        _tool("get_capabilities", "Получить возможности транспорта, лимиты и справочники.", {}),
        _tool("review_snapshot", "Получить отчёт и lint для ревью без байтов изображений и изменения состояния.", {}),
        _tool(
            "list_images",
            "Получить список прикреплённых изображений и их SHA-256.",
            {},
        ),
        _tool(
            "get_image",
            "Получить изображение как нативный MCP Image Content.",
            {"filename": {"type": "string"}},
            ["filename"],
        ),
        _tool(
            "get_images",
            "Получить несколько изображений как нативный MCP Image Content.",
            {"filenames": {"type": "array", "minItems": 1, "maxItems": 16,
                            "items": {"type": "string"}}},
            ["filenames"],
        ),
        _tool(
            "upload_image",
            "Загрузить изображение в RAM; существующие имена не заменяются.",
            {
                "filename": {"type": "string"},
                "base64_data": {"type": "string"},
                "file_path": {"type": "string", "description": "Путь к изображению на машине сервера; поддерживает ~ и относительные пути"},
                "expected_image_revision": revision,
                "expected_revision": revision,
                "caption": {"type": "string"},
                "insert_into_report": {"type": "boolean", "default": False},
            },
            ["filename", "expected_image_revision"],
            **IMAGE_SOURCE_SCHEMA,
        ),
        _tool(
            "upload_images",
            "Последовательно загрузить несколько изображений с одной проверкой версии; вернуть ошибки отдельных файлов.",
            {
                "images": {
                    "type": "array", "minItems": 1, "maxItems": MAX_IMAGES_COUNT,
                    "items": {
                        "type": "object", "required": ["filename"],
                        "properties": {
                            "filename": {"type": "string"}, "base64_data": {"type": "string"},
                            "file_path": {"type": "string"}, "caption": {"type": "string"},
                            "insert_into_report": {"type": "boolean", "default": False},
                        },
                        **IMAGE_SOURCE_SCHEMA,
                    },
                },
                "expected_image_revision": revision,
                "expected_revision": revision,
            },
            ["images", "expected_image_revision"],
        ),
        _tool(
            "append_or_update_section",
            "Добавить раздел или заменить его тело по свежей revision текста.",
            {
                "section_heading": {"type": "string"},
                "section_content": {"type": "string"},
                "expected_revision": revision,
            },
            ["section_heading", "section_content", "expected_revision"],
        ),
        _tool(
            "update_meta",
            "Точечно обновить реквизиты по свежей meta_revision.",
            {"fields": {"type": "object"}, "expected_meta_revision": revision},
            ["fields", "expected_meta_revision"],
        ),
        _tool(
            "delete_image",
            "Удалить неиспользуемое изображение по свежей image_revision.",
            {"filename": {"type": "string"}, "expected_image_revision": revision},
            ["filename", "expected_image_revision"],
        ),
        _tool("lint_report", "Проверить текущий отчёт по ГОСТ.", {}, []),
        _tool(
            "autofix_typography",
            "Применить типографику к текущему Markdown по свежей revision.",
            {"expected_revision": revision},
            ["expected_revision"],
        ),
    ]
    formats = ["docx", "pdf"] if pdf_export_enabled() else ["docx"]
    tools.append(_tool(
        "export_report",
        "Явно сохранить новый DOCX или PDF в папку, заданную при запуске процесса.",
        {
            "filename": {"type": "string", "description": "Только имя файла, без пути"},
            "format": {"type": "string", "enum": formats},
            "expected_revision": revision,
            "expected_meta_revision": revision,
            "expected_image_revision": revision,
            "confirm_blocked_export": {"type": "boolean", "default": False},
        },
        ["filename", "expected_revision", "expected_meta_revision", "expected_image_revision"],
    ))
    unified_fields = {
        "expected_snapshot_id": {
            "type": "string",
            "description": "Атомарная snapshot_id из get_report_state; заменяет отдельные expected_*",
        },
        "operation_id": {
            "type": "string",
            "description": "Необязательный ключ идемпотентности для безопасного повтора операции",
        },
    }
    for tool in tools:
        if tool.name not in HEADLESS_MUTATING_TOOLS and tool.name != "batch":
            continue
        tool.input_schema.setdefault("properties", {}).update(unified_fields)
    return tools


def _resources(report: HeadlessReport) -> list[types.Resource]:
    result = [
        types.Resource(
            uri="report://rules/gost732",
            name="Инструкция агента",
            description="Канонические правила оформления отчёта",
            mimeType="text/markdown",
        ),
        types.Resource(
            uri="report://document/current",
            name="Текущий текст отчёта",
            description="Markdown текущего headless-отчёта",
            mimeType="text/markdown",
        ),
    ]
    result.extend(types.Resource(**resource) for resource in reference_resources())
    try:
        for image in report.list_images():
            result.append(types.Resource(
                uri=f"report://image/{image['filename']}",
                name=f"Изображение: {image['filename']}",
                description="Изображение отчёта",
                mimeType=image["mime_type"],
            ))
    except ValueError:
        pass
    return result


HEADLESS_MUTATING_TOOLS = frozenset({
    "create_report", "import_profile", "upload_image", "upload_images",
    "append_or_update_section", "update_meta", "delete_image",
    "autofix_typography", "export_report",
})


def _dispatch_tool(report: HeadlessReport, name: str, args: dict[str, Any]) -> types.CallToolResult:
    """Deduplicate successful mutation calls before dispatching them."""
    is_mutating = name in HEADLESS_MUTATING_TOOLS or (
        name == "batch" and any(call.get("name") in HEADLESS_MUTATING_TOOLS
                                 for call in args.get("calls", []) if isinstance(call, dict))
    )
    operation_id = args.get("operation_id")
    if is_mutating and operation_id is not None:
        try:
            cached = report.operation_cache.lookup(operation_id, args, name)
        except (TypeError, ValueError) as exc:
            return _text_result(str(exc), is_error=True)
        if cached is not None:
            return cached
    result = _dispatch_tool_uncached(report, name, args)
    if is_mutating and operation_id is not None and not result.is_error:
        report.operation_cache.store(operation_id, args, result, name)
    return result


def _dispatch_tool_uncached(report: HeadlessReport, name: str, args: dict[str, Any]) -> types.CallToolResult:
    """Dispatch one headless tool with the same error handling inside batches."""
    try:
        if name == "batch":
            calls = validate_batch_calls(args)
            results = []
            previous_results = []
            for call in calls:
                try:
                    call_args = resolve_batch_arguments(call["arguments"], previous_results)
                    response = _dispatch_tool(report, call["name"], call_args)
                    if response.is_error:
                        error = response.structured_content or "\n".join(
                            block.text for block in response.content if isinstance(block, types.TextContent)
                        )
                        results.append({"name": call["name"], "ok": False, "error": error})
                        previous_results.append(None)
                        if args.get("stop_on_error", False):
                            break
                    else:
                        value = response.structured_content
                        if value is None:
                            value = response.model_dump(mode="json", by_alias=True, exclude_none=True)
                        results.append({"name": call["name"], "ok": True, "result": value})
                        previous_results.append(value)
                except (TypeError, ValueError, OSError, RuntimeError) as exc:
                    results.append({"name": call["name"], "ok": False, "error": str(exc)})
                    previous_results.append(None)
                    if args.get("stop_on_error", False):
                        break
            return _text_result(results)
        if name == "create_report":
            return _text_result(report.create_report(_object(args, "metadata", required=False)))
        if name == "import_profile":
            expected = args.get("expected_meta_revision")
            if expected is not None and not isinstance(expected, str):
                raise ValueError("Параметр «expected_meta_revision» должен быть строкой")
            return _text_result(report.import_profile(
                load_profile_input(args), expected,
                expected_snapshot_id=args.get("expected_snapshot_id"),
            ))
        if name == "get_report_state":
            return _text_result(report.get_report_state(args.get("detail", "full")))
        if name == "get_capabilities":
            return _text_result(get_capabilities("headless"))
        if name == "review_snapshot":
            return _text_result(report.review_snapshot())
        if name == "list_images":
            return _text_result({"images": report.list_images()})
        if name == "get_image":
            filename = _string(args, "filename")
            data = report.get_image(filename)
            image_type = mimetypes.guess_type(filename)[0] or "image/png"
            return types.CallToolResult(content=[
                types.ImageContent(data=base64.b64encode(data).decode("ascii"), mimeType=image_type),
                types.TextContent(text=f"Изображение «{filename}» получено"),
            ])
        if name == "get_images":
            filenames = args.get("filenames")
            if not isinstance(filenames, list) or not 1 <= len(filenames) <= 16:
                raise ValueError("Ожидается от 1 до 16 имён изображений")
            content = []
            for filename in filenames:
                safe_name = _string({"filename": filename}, "filename")
                data = report.get_image(safe_name)
                content.append(types.ImageContent(
                    data=base64.b64encode(data).decode("ascii"),
                    mimeType=mimetypes.guess_type(safe_name)[0] or "image/png",
                ))
            content.append(types.TextContent(text=f"Пакетно получено изображений: {len(filenames)}"))
            return types.CallToolResult(content=content)
        if name == "upload_image":
            expected_revision = args.get("expected_revision")
            expected_image = (args.get("expected_image_revision")
                              if args.get("expected_snapshot_id") is None else None)
            if expected_image is None and args.get("expected_snapshot_id") is None:
                expected_image = expected_revision
            result = report.upload_image(
                _string(args, "filename"), load_image_input(args, _decode_image),
                _string({"expected_image_revision": expected_image}, "expected_image_revision")
                if args.get("expected_snapshot_id") is None else None,
                caption=str(args.get("caption", "")),
                insert_into_report=bool(args.get("insert_into_report", False)),
                expected_revision=expected_revision if isinstance(expected_revision, str) else None,
                expected_snapshot_id=args.get("expected_snapshot_id"),
            )
            return _text_result(result)
        if name == "upload_images":
            items = args.get("images")
            if not isinstance(items, list) or not 1 <= len(items) <= MAX_IMAGES_COUNT:
                raise ValueError(f"Ожидается от 1 до {MAX_IMAGES_COUNT} изображений")
            expected_image = (args.get("expected_image_revision") or args.get("expected_revision")
                              if args.get("expected_snapshot_id") is None else None)
            if args.get("expected_snapshot_id") is None and not isinstance(expected_image, str):
                raise ValueError("Параметр «expected_image_revision» должен быть непустой строкой")
            prepared = []
            for item in items:
                if not isinstance(item, dict):
                    prepared.append(item)
                    continue
                image = {key: item[key] for key in ("filename", "caption", "insert_into_report") if key in item}
                try:
                    image["data"] = load_image_input(item, _decode_image)
                except (ValueError, OSError) as exc:
                    image["error"] = str(exc)
                prepared.append(image)
            return _text_result(report.upload_images(
                prepared, expected_image, expected_revision=args.get("expected_revision"),
                expected_snapshot_id=args.get("expected_snapshot_id"),
            ))
        if name == "append_or_update_section":
            return _text_result(report.append_or_update_section(
                _string(args, "section_heading"), _string(args, "section_content", required=False),
                _string(args, "expected_revision") if args.get("expected_snapshot_id") is None else None,
                expected_snapshot_id=args.get("expected_snapshot_id"),
            ))
        if name == "update_meta":
            fields = args.get("fields")
            if fields is None:
                allowed = {
                    "work_theme", "work_number", "work_type", "discipline", "institute",
                    "department", "university", "ministry", "city", "year",
                    "teachers", "students", "references", "custom_instructions",
                }
                fields = {key: value for key, value in args.items() if key in allowed}
            return _text_result(report.update_meta(
                fields if isinstance(fields, dict) else _object(args, "fields"),
                _string(args, "expected_meta_revision") if args.get("expected_snapshot_id") is None else None,
                expected_snapshot_id=args.get("expected_snapshot_id"),
            ))
        if name == "delete_image":
            return _text_result(report.delete_image(
                _string(args, "filename"),
                _string({"expected_image_revision": args.get("expected_image_revision") or args.get("expected_revision")},
                        "expected_image_revision") if args.get("expected_snapshot_id") is None else None,
                expected_snapshot_id=args.get("expected_snapshot_id"),
            ))
        if name == "lint_report":
            return _text_result(report.lint_report())
        if name == "autofix_typography":
            return _text_result(report.autofix_typography(
                _string(args, "expected_revision") if args.get("expected_snapshot_id") is None else None,
                expected_snapshot_id=args.get("expected_snapshot_id"),
            ))
        if name == "export_report":
            return _text_result(report.export_report(
                _string(args, "filename"),
                _string(args, "expected_revision") if args.get("expected_snapshot_id") is None else None,
                _string(args, "expected_meta_revision") if args.get("expected_snapshot_id") is None else None,
                _string(args, "expected_image_revision") if args.get("expected_snapshot_id") is None else None,
                args.get("format") if isinstance(args.get("format"), str) else None,
                args.get("confirm_blocked_export", False),
                expected_snapshot_id=args.get("expected_snapshot_id"),
            ))
        raise ValueError(f"Неизвестный инструмент: {name}")
    except (TypeError, ValueError, OSError, RuntimeError) as exc:
        message = str(exc)
        if is_conflict_message(message):
            return _text_result(conflict_payload(message, report._revisions()), is_error=True)
        return _text_result(message, is_error=True)


def _make_server(report: HeadlessReport) -> Server:
    async def list_tools(_ctx: Any, _params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=_tools())

    async def call_tool(_ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        return _dispatch_tool(report, params.name, params.arguments or {})

    async def list_resources(_ctx: Any, _params: Any) -> types.ListResourcesResult:
        return types.ListResourcesResult(resources=_resources(report))

    async def read_resource(_ctx: Any, params: types.ReadResourceRequestParams) -> types.ReadResourceResult:
        uri = params.uri
        if uri.startswith("report://reference/"):
            return types.ReadResourceResult(contents=[types.TextResourceContents(
                uri=uri, mimeType="text/markdown", text=read_reference(uri),
            )])
        if uri == "report://rules/gost732":
            return types.ReadResourceResult(contents=[types.TextResourceContents(
                uri=uri, mimeType="text/markdown", text=_skill_text(),
            )])
        if uri == "report://document/current":
            state = report.get_report_state()
            return types.ReadResourceResult(contents=[types.TextResourceContents(
                uri=uri, mimeType="text/markdown", text=state["markdown_content"],
            )])
        prefix = "report://image/"
        if uri.startswith(prefix):
            filename = uri[len(prefix):]
            data = report.get_image(filename)
            mime_type = mimetypes.guess_type(filename)[0] or "image/png"
            return types.ReadResourceResult(contents=[types.BlobResourceContents(
                uri=uri, mimeType=mime_type, blob=base64.b64encode(data).decode("ascii"),
            )])
        raise ValueError("Ресурс не найден")

    async def list_prompts(_ctx: Any, _params: Any) -> types.ListPromptsResult:
        return types.ListPromptsResult(prompts=[types.Prompt(
            name="write_report",
            description="Вести отчёт по ГОСТ через локальный headless MCP",
            arguments=[types.PromptArgument(name="task", description="Задание пользователя")],
        )])

    async def get_prompt(_ctx: Any, params: types.GetPromptRequestParams) -> types.GetPromptResult:
        task = (params.arguments or {}).get("task", "")
        instructions = (
            "Ты работаешь с локальным headless Report Engine без браузера. "
            "Сначала вызови get_report_state; если отчёт ещё не создан, вызови create_report. "
            "Для каждой записи используй свежую соответствующую revision. "
            "После правок вызови lint_report, затем export_report только по явной задаче.\n\n"
            + _skill_text()
        )
        if task:
            instructions += f"\n\nЗадание пользователя: {task}"
        return types.GetPromptResult(
            description="Работа с отчётом в headless-режиме",
            messages=[types.PromptMessage(role="user", content=types.TextContent(text=instructions))],
        )

    return Server(
        "report-engine-headless",
        version=SERVER_VERSION,
        instructions="Локальный MCP-сервер Report Engine. Состояние живёт только в RAM до остановки процесса.",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        on_list_resources=list_resources,
        on_read_resource=read_resource,
        on_list_prompts=list_prompts,
        on_get_prompt=get_prompt,
    )


async def _run(output_dir: Path) -> None:
    report = HeadlessReport(output_dir)
    server = _make_server(report)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local headless Report Engine MCP server")
    parser.add_argument("--output-dir", required=True, type=Path, help="Existing directory for explicit exports")
    args = parser.parse_args()
    try:
        import asyncio
        asyncio.run(_run(args.output_dir))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
