"""Shared discovery and preflight validation for sequential MCP batches."""

from typing import Any


BATCH_SCHEMA = {
    "type": "object",
    "required": ["calls"],
    "properties": {
        "calls": {
            "type": "array", "minItems": 1, "maxItems": 20,
            "items": {
                "type": "object", "required": ["name", "arguments"],
                "properties": {"name": {"type": "string"}, "arguments": {"type": "object"}},
            },
        },
        "stop_on_error": {"type": "boolean", "default": False},
    },
}


def validate_batch_calls(args: dict[str, Any]) -> list[dict[str, Any]]:
    """Reject malformed or nested batches before any contained tool runs."""
    calls = args.get("calls")
    if not isinstance(calls, list) or not 1 <= len(calls) <= 20:
        raise ValueError("Параметр calls должен содержать от 1 до 20 вызовов")
    if not isinstance(args.get("stop_on_error", False), bool):
        raise ValueError("Параметр stop_on_error должен быть логическим значением")
    for call in calls:
        if (not isinstance(call, dict) or not isinstance(call.get("name"), str)
                or not call["name"].strip() or not isinstance(call.get("arguments"), dict)):
            raise ValueError("Каждый вызов требует непустое имя name и объект arguments")
        if call["name"] == "batch":
            raise ValueError("Вложенный batch запрещён; весь массив calls отклонён")
    return calls
