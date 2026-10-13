"""Shared image limits and local-file input for both MCP transports."""

from pathlib import Path
from typing import Any, Callable


MAX_IMAGE_SIZE = 15 * 1024 * 1024
MAX_IMAGES_COUNT = 150
IMAGE_SOURCE_SCHEMA = {
    "oneOf": [{"required": ["base64_data"]}, {"required": ["file_path"]}],
}


def load_image_input(args: dict[str, Any], decode_base64: Callable[[str], bytes]) -> bytes:
    """Read exactly one image source with bounded local-file reads.

    The supplied decoder preserves each transport's existing base64 validation.
    Local paths refer to the server filesystem, not the remote agent's machine.
    """
    encoded = args.get("base64_data")
    file_path = args.get("file_path")
    if (encoded is None) == (file_path is None):
        raise ValueError("Передайте base64_data или file_path, но не оба параметра")
    if encoded is not None:
        if not isinstance(encoded, str) or not encoded.strip():
            raise ValueError("Параметр base64_data должен быть непустой строкой")
        return decode_base64(encoded)
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("Параметр file_path должен быть непустой строкой")
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
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
