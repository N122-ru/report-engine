#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${REPORT_ENGINE_OUTPUT_DIR:-$ROOT_DIR/output}"
echo 'Конструктор отчётов: MCP-сервер без браузерного интерфейса.' >&2
echo 'Для работы нужен MCP-клиент, например ИИ-агент с поддержкой stdio.' >&2
echo 'Ожидание клиента — нормальное поведение. Настройка описана в README.md рядом с этим файлом.' >&2

if mkdir -p "$OUTPUT_DIR" && "$ROOT_DIR/report-engine-headless" --output-dir "$OUTPUT_DIR" "$@"; then
  exit 0
else
  RESULT=$?
  echo 'Не удалось запустить MCP-сервер или сохранить отчёт. Проверьте сообщения выше, целостность пакета и права на папку вывода.' >&2
  echo "Инструкция и устранение неполадок: $ROOT_DIR/README.md." >&2
  if [[ -t 0 && -t 2 ]]; then read -r -p 'Нажмите Enter, чтобы закрыть окно. ' || true; fi
  exit "$RESULT"
fi
