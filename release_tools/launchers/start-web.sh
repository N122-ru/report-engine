#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PORT=8000
OPEN_BROWSER=1
ARGS=("$@")
for ((index=0; index<${#ARGS[@]}; index++)); do
  case "${ARGS[index]}" in
    --port) PORT="${ARGS[index+1]:-}" ;;
    --port=*) PORT="${ARGS[index]#--port=}" ;;
    --help|-h) OPEN_BROWSER=0 ;;
  esac
done
URL="http://127.0.0.1:$PORT"
echo "Веб-интерфейс: $URL"
echo 'Оставьте это окно открытым во время работы. Для остановки нажмите Ctrl+C.'

"$ROOT_DIR/report-engine-web" "$@" &
SERVER_PID=$!
BROWSER_PID=''
trap 'kill "$SERVER_PID" ${BROWSER_PID:+"$BROWSER_PID"} 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

open_browser() {
  # A health check prevents opening the SPA before the server is ready.
  for ((attempt=0; attempt<120; attempt++)); do
    sleep 0.25
    kill -0 "$SERVER_PID" 2>/dev/null || return 0
    if curl --fail --silent --max-time 1 "$URL/api/health" >/dev/null 2>&1; then
      if command -v xdg-open >/dev/null; then
        xdg-open "$URL" >/dev/null 2>&1 || true
      elif command -v gio >/dev/null; then
        gio open "$URL" >/dev/null 2>&1 || true
      fi
      return 0
    fi
  done
}

if [[ "$OPEN_BROWSER" == 1 && -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && command -v curl >/dev/null; then
  open_browser &
  BROWSER_PID=$!
fi
if wait "$SERVER_PID"; then
  exit 0
else
  RESULT=$?
  echo 'Не удалось запустить веб-интерфейс. Проверьте сообщения выше: порт может быть занят или пакет распакован не полностью.' >&2
  echo "Попробуйте другой порт: start-web.sh --port 8001. Инструкция: $ROOT_DIR/README.md." >&2
  if [[ -t 0 && -t 2 ]]; then read -r -p 'Нажмите Enter, чтобы закрыть окно. ' || true; fi
  exit "$RESULT"
fi
