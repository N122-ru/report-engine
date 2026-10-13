"""Read the product version from the repository or frozen application bundle."""

from __future__ import annotations

import re
from pathlib import Path


VERSION_FILE = "VERSION"
_VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def read_version(path: Path | None = None) -> str:
    """Return a validated SemVer string from the canonical version file."""
    version_path = path or Path(__file__).resolve().parents[2] / VERSION_FILE
    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Не найден файл версии продукта: {version_path}") from exc
    if not _VERSION_PATTERN.fullmatch(version):
        raise RuntimeError(f"Некорректная версия продукта в {version_path}: {version!r}")
    return version


APP_VERSION = read_version()
