"""Shared image limits and local-file input for both MCP transports."""

from pathlib import Path
from typing import Any, Callable


MAX_IMAGE_SIZE = 15 * 1024 * 1024
MAX_IMAGES_COUNT = 150
MAX_BASE64_IMAGE_LENGTH = ((MAX_IMAGE_SIZE + 2) // 3) * 4
IMAGE_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a",
)
IMAGE_SOURCE_SCHEMA = {
    "oneOf": [{"required": ["base64_data"]}, {"required": ["file_path"]}],
}


def resolve_file_path(file_path: str) -> Path:
    """Resolve a server-local source path, expanding `~` and relative paths."""
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("Параметр file_path должен быть непустой строкой")
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Файл изображения не найден") from exc


def validate_image_data(data: bytes) -> None:
    """Validate image magic bytes in addition to the transport size limit."""
    if not isinstance(data, bytes) or not data:
        raise ValueError("Данные изображения пусты")
    valid_signature = data.startswith(IMAGE_SIGNATURES) or (
        data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP"
    )
    if not valid_signature:
        raise ValueError("Данные не похожи на поддерживаемое изображение")


def load_image_input(
    args: dict[str, Any], decode_base64: Callable[[str], bytes],
) -> bytes:
    """Read exactly one image source with bounded local-file reads.

    The supplied decoder preserves each transport's existing base64 validation.
    Local paths refer to the server filesystem and are admitted only by callers
    that already verified a local run; reads stay bounded here.
    """
    encoded = args.get("base64_data")
    file_path = args.get("file_path")
    if (encoded is None) == (file_path is None):
        raise ValueError("Передайте base64_data или file_path, но не оба параметра")
    if encoded is not None:
        if not isinstance(encoded, str) or not encoded.strip():
            raise ValueError("Параметр base64_data должен быть непустой строкой")
        normalized = encoded.strip()
        if "base64," in normalized[:64].lower():
            normalized = normalized.split(",", 1)[1]
        if len(normalized) > MAX_BASE64_IMAGE_LENGTH:
            raise ValueError(f"Закодированное изображение превышает лимит {MAX_IMAGE_SIZE // (1024 * 1024)} МБ")
        return decode_base64(encoded)
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("Параметр file_path должен быть непустой строкой")
    path = resolve_file_path(file_path)
    try:
        if not path.is_file():
            raise ValueError("Файл изображения не найден")
        if path.stat().st_size > MAX_IMAGE_SIZE:
            raise ValueError(f"Размер изображения превышает {MAX_IMAGE_SIZE // (1024 * 1024)} МБ")
        with path.open("rb") as source:
            data = source.read(MAX_IMAGE_SIZE + 1)
    except OSError as exc:
        raise ValueError("Не удалось прочитать файл изображения") from exc
    if not data:
        raise ValueError("Данные изображения пусты")
    if len(data) > MAX_IMAGE_SIZE:
        raise ValueError(f"Размер изображения превышает {MAX_IMAGE_SIZE // (1024 * 1024)} МБ")
    return data
