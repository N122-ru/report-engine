#!/usr/bin/env bash
# ==============================================================================
# Launch the local GOST 7.32 report generator.
# ==============================================================================

set -e

# Terminal output colors.
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # Без цвета

# Resolve the project root relative to this script.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

BACKEND_PORT=8000
FRONTEND_PORT=5173

# Shared process IDs.
BACKEND_PID=""
FRONTEND_PID=""

# ------------------------------------------------------------------------------
# Load nvm when Node.js or npm is absent from PATH.
# ------------------------------------------------------------------------------
load_nvm() {
    if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
        if [ -s "$HOME/.nvm/nvm.sh" ]; then
            export NVM_DIR="$HOME/.nvm"
            # shellcheck disable=SC1090
            \. "$NVM_DIR/nvm.sh"
        fi
    fi
}

# ------------------------------------------------------------------------------
# Startup banner.
# ------------------------------------------------------------------------------
print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "=================================================================="
    echo "   Конструктор отчётов по ГОСТ 7.32"
    echo "   Генератор и нормоконтроль отчетов по ГОСТ 7.32"
    echo "=================================================================="
    echo -e "${NC}"
}

# ------------------------------------------------------------------------------
# Command help.
# ------------------------------------------------------------------------------
show_help() {
    print_banner
    echo -e "${BOLD}Использование:${NC}"
    echo "  ./start.sh [команда] [опции]"
    echo ""
    echo -e "${BOLD}Команды:${NC}"
    echo -e "  ${GREEN}dev${NC} (по умолчанию)  Запуск в режиме разработки (FastAPI на :${BACKEND_PORT} + Vite на :${FRONTEND_PORT})"
    echo -e "  ${GREEN}prod${NC} | ${GREEN}build${NC}        Сборка фронтенда и запуск в едином процессе на :${BACKEND_PORT}"
    echo -e "  ${YELLOW}stop${NC}                Остановить все запущенные процессы проекта"
    echo -e "  ${YELLOW}restart [dev|prod]${NC}  Перезапустить сервисы"
    echo -e "  ${BLUE}status${NC}              Проверить статус сервисов и доступность портов"
    echo -e "  ${BLUE}test${NC}                Запустить тесты (pytest)"
    echo -e "  ${CYAN}help${NC} | ${CYAN}--help${NC}       Показать эту справку"
    echo ""
    echo -e "${BOLD}Опции:${NC}"
    echo "  -f, --force         Автоматически освобождать занятые порты перед стартом"
    echo ""
    echo -e "${BOLD}Примеры:${NC}"
    echo "  ./start.sh          # Быстрый запуск для работы"
    echo "  ./start.sh prod     # Запуск единого сервера на :8000"
    echo "  ./start.sh stop     # Остановка"
    echo ""
}

# ------------------------------------------------------------------------------
# Terminate the process tree by PID.
# ------------------------------------------------------------------------------
kill_tree() {
    local pid=$1
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        pkill -P "$pid" 2>/dev/null || true
        kill -TERM "$pid" 2>/dev/null || true
    fi
}

# ------------------------------------------------------------------------------
# Release an occupied port.
# ------------------------------------------------------------------------------
free_port() {
    local port=$1
    if command -v lsof >/dev/null 2>&1; then
        local pids
        pids=$(lsof -ti :"$port" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo -e "${YELLOW}Освобождаем порт $port (PID: $pids)...${NC}"
            kill $pids 2>/dev/null || true
            sleep 0.5
    # Force termination if processes are still alive.
            pids=$(lsof -ti :"$port" 2>/dev/null || true)
            if [ -n "$pids" ]; then
                kill -9 $pids 2>/dev/null || true
            fi
        fi
    fi
}

# ------------------------------------------------------------------------------
# Check whether a port is occupied.
# ------------------------------------------------------------------------------
is_port_in_use() {
    local port=$1
    if command -v lsof >/dev/null 2>&1; then
        lsof -i :"$port" >/dev/null 2>&1
        return $?
    elif command -v ss >/dev/null 2>&1; then
        ss -tulwn | grep -q ":$port "
        return $?
    fi
    return 1
}

# ------------------------------------------------------------------------------
# Locate a Python interpreter with the required dependencies.
# ------------------------------------------------------------------------------
check_python() {
    echo -e "${BLUE}▶ Проверка окружения Python...${NC}"
    
    # Prefer the backend virtual environment.
    if [ -f "$BACKEND_DIR/venv/bin/python3" ] && "$BACKEND_DIR/venv/bin/python3" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
        PYTHON_EXEC="$BACKEND_DIR/venv/bin/python3"
        echo -e "${GREEN}✓ Используется Python venv:${NC} $PYTHON_EXEC"
        return 0
    fi

    # Fall back to system Python.
    if command -v python3 >/dev/null 2>&1 && python3 -c "import fastapi, uvicorn" >/dev/null 2>&1; then
        PYTHON_EXEC="python3"
        echo -e "${GREEN}✓ Используется системный Python:${NC} $(python3 --version 2>&1)"
        return 0
    fi

    # Create a virtual environment when dependencies are missing.
    if command -v python3 >/dev/null 2>&1; then
        echo -e "${YELLOW}Настройка виртуального окружения Python в $BACKEND_DIR/venv...${NC}"
        if [ ! -d "$BACKEND_DIR/venv" ]; then
            python3 -m venv "$BACKEND_DIR/venv" --system-site-packages
        fi
        PYTHON_EXEC="$BACKEND_DIR/venv/bin/python3"
        
        echo -e "${YELLOW}Установка зависимостей из requirements.txt...${NC}"
        "$PYTHON_EXEC" -m pip install -r "$BACKEND_DIR/requirements.txt" || {
            echo -e "${RED}Ошибка установки зависимостей Python!${NC}"
            exit 1
        }
        echo -e "${GREEN}✓ Зависимости Python установлены.${NC}"
        return 0
    fi

    echo -e "${RED}❌ Ошибка: Python 3 не найден в системе!${NC}"
    echo "Пожалуйста, установите Python 3 (версии 3.11+) и повторите попытку."
    exit 1
}

# ------------------------------------------------------------------------------
# Check Node.js and frontend dependencies.
# ------------------------------------------------------------------------------
check_node() {
    load_nvm
    echo -e "${BLUE}▶ Проверка окружения Node.js...${NC}"

    if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
        echo -e "${RED}❌ Ошибка: Node.js или npm не найдены в системе!${NC}"
        echo "Пожалуйста, установите Node.js (версии 20.19+ или 22.12+) для работы веб-интерфейса."
        exit 1
    fi

    echo -e "${GREEN}✓ Node.js:${NC} $(node -v) (npm: $(npm -v))"

    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        echo -e "${YELLOW}Установка зависимостей фронтенда (npm install)...${NC}"
        (cd "$FRONTEND_DIR" && npm install)
        echo -e "${GREEN}✓ Зависимости фронтенда установлены.${NC}"
    else
        echo -e "${GREEN}✓ Зависимости фронтенда (node_modules) готовы.${NC}"
    fi
}

# ------------------------------------------------------------------------------
# Detect an optional PDF converter.
# ------------------------------------------------------------------------------
check_pdf_converter() {
    if command -v libreoffice >/dev/null 2>&1 || command -v soffice >/dev/null 2>&1 || command -v docbuilder >/dev/null 2>&1; then
        echo -e "${GREEN}✓ PDF-конвертер найден (экспорт в PDF активен).${NC}"
    else
        echo -e "${YELLOW}⚠️ PDF-конвертер не найден.${NC}"
        echo -e "  Генерация .docx доступна, PDF можно получить вручную в Office/OnlyOffice."
    fi
}

# ------------------------------------------------------------------------------
# Stop running services.
# ------------------------------------------------------------------------------
stop_services() {
    print_banner
    echo -e "${YELLOW}Остановка сервисов...${NC}"
    free_port "$BACKEND_PORT"
    free_port "$FRONTEND_PORT"
    echo -e "${GREEN}✓ Сервисы остановлены.${NC}"
}

# ------------------------------------------------------------------------------
# Check service status.
# ------------------------------------------------------------------------------
check_status() {
    print_banner
    echo -e "${BOLD}Статус сервисов:${NC}\n"

    # Backend
    if is_port_in_use "$BACKEND_PORT"; then
        echo -e "  • Бэкенд (: $BACKEND_PORT):  ${GREEN}запущен (порт занят)${NC}"
        if command -v curl >/dev/null 2>&1; then
            local health
            health=$(curl -s "http://127.0.0.1:$BACKEND_PORT/api/health" || true)
            if [[ "$health" =~ '"status": *"ok"' ]]; then
                echo -e "    ${GREEN}✓ API отвечает корректно (/api/health ok)${NC}"
            else
                echo -e "    ${YELLOW}⚠️ На порту $BACKEND_PORT работает другой процесс${NC}"
            fi
        fi
    else
        echo -e "  • Бэкенд (: $BACKEND_PORT):  ${RED}остановлен${NC}"
    fi

    # Frontend
    if is_port_in_use "$FRONTEND_PORT"; then
        echo -e "  • Фронтенд (: $FRONTEND_PORT): ${GREEN}запущен (порт занят)${NC}"
    else
        echo -e "  • Фронтенд (: $FRONTEND_PORT): ${RED}остановлен${NC}"
    fi
    echo ""
}

# ------------------------------------------------------------------------------
# Run tests.
# ------------------------------------------------------------------------------
run_tests() {
    print_banner
    check_python
    echo -e "\n${BLUE}▶ Запуск тестов pytest...${NC}\n"
    "$PYTHON_EXEC" -m pytest tests/ -v
}

# ------------------------------------------------------------------------------
# Start development mode with FastAPI and Vite.
# ------------------------------------------------------------------------------
start_dev() {
    local force=$1
    print_banner
    check_python
    check_node
    check_pdf_converter
    echo ""

    # Check required ports before startup.
    if is_port_in_use "$BACKEND_PORT"; then
        if [ "$force" = "true" ]; then
            free_port "$BACKEND_PORT"
        else
            echo -e "${RED}❌ Порт $BACKEND_PORT уже занят!${NC}"
            echo -e "Используйте ${BOLD}./start.sh stop${NC} или добавьте флаг ${BOLD}--force${NC} для перезапуска."
            exit 1
        fi
    fi

    if is_port_in_use "$FRONTEND_PORT"; then
        if [ "$force" = "true" ]; then
            free_port "$FRONTEND_PORT"
        else
            echo -e "${RED}❌ Порт $FRONTEND_PORT уже занят!${NC}"
            echo -e "Используйте ${BOLD}./start.sh stop${NC} или добавьте флаг ${BOLD}--force${NC} для перезапуска."
            exit 1
        fi
    fi

    # Clean up processes on Ctrl+C.
    cleanup_dev() {
        echo -e "\n\n${YELLOW}Завершение работы...${NC}"
        kill_tree "$BACKEND_PID"
        kill_tree "$FRONTEND_PID"
        free_port "$BACKEND_PORT"
        free_port "$FRONTEND_PORT"
        echo -e "${GREEN}✓ Все процессы остановлены. До свидания!${NC}"
        exit 0
    }
    trap cleanup_dev INT TERM

    echo -e "${CYAN}Запуск сервисов в режиме разработки (Dev Mode)...${NC}\n"

    # Start FastAPI.
    echo -e "${BLUE}▶ Запуск FastAPI бэкенда на порту $BACKEND_PORT...${NC}"
    "$PYTHON_EXEC" -m uvicorn backend.app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" --proxy-headers --forwarded-allow-ips=* --reload &
    BACKEND_PID=$!

    # Start Vite.
    echo -e "${BLUE}▶ Запуск Vite фронтенда на порту $FRONTEND_PORT...${NC}"
    (cd "$FRONTEND_DIR" && npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT") &
    FRONTEND_PID=$!

    # Allow time for service initialization.
    sleep 2

    echo -e "\n${GREEN}${BOLD}Сервисы запущены.${NC}"
    echo "=================================================================="
    echo -e "  ${BOLD}Веб-интерфейс:${NC}      ${CYAN}http://localhost:${FRONTEND_PORT}${NC}"
    echo -e "  ${BOLD}API Сервер:${NC}         ${CYAN}http://localhost:${BACKEND_PORT}${NC}"
    echo -e "  ${BOLD}Swagger документация:${NC} ${CYAN}http://localhost:${BACKEND_PORT}/docs${NC}"
    echo "=================================================================="
    echo -e "${YELLOW}Для остановки нажмите ${BOLD}Ctrl + C${NC}\n"

    # Wait for service processes.
    wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}

# ------------------------------------------------------------------------------
# Start standalone mode with the built SPA and FastAPI.
# ------------------------------------------------------------------------------
start_prod() {
    local force=$1
    print_banner
    check_python
    check_node
    check_pdf_converter
    echo ""

    if is_port_in_use "$BACKEND_PORT"; then
        if [ "$force" = "true" ]; then
            free_port "$BACKEND_PORT"
        else
            echo -e "${RED}❌ Порт $BACKEND_PORT уже занят!${NC}"
            echo -e "Используйте ${BOLD}./start.sh stop${NC} или добавьте флаг ${BOLD}--force${NC} для перезапуска."
            exit 1
        fi
    fi

    # Build the frontend when dist is absent or a full rebuild is requested.
    echo -e "${BLUE}▶ Сборка React фронтенда (npm run build)...${NC}"
    (cd "$FRONTEND_DIR" && npm run build)
    echo -e "${GREEN}✓ Фронтенд собран в frontend/dist.${NC}\n"

    cleanup_prod() {
        echo -e "\n\n${YELLOW}Завершение работы...${NC}"
        kill_tree "$BACKEND_PID"
        free_port "$BACKEND_PORT"
        echo -e "${GREEN}✓ Сервер остановлен. До свидания!${NC}"
        exit 0
    }
    trap cleanup_prod INT TERM

    echo -e "${CYAN}Запуск единого автономного сервера на порту $BACKEND_PORT...${NC}\n"
    echo -e "\n${GREEN}${BOLD}Сервер запущен в автономном режиме.${NC}"
    echo "=================================================================="
    echo -e "  ${BOLD}Веб-приложение:${NC}     ${CYAN}http://localhost:${BACKEND_PORT}${NC}"
    echo -e "  ${BOLD}API Swagger:${NC}        ${CYAN}http://localhost:${BACKEND_PORT}/docs${NC}"
    echo "=================================================================="
    echo -e "${YELLOW}Для остановки нажмите ${BOLD}Ctrl + C${NC}\n"

    "$PYTHON_EXEC" -m uvicorn backend.app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" --proxy-headers --forwarded-allow-ips=*
}

# ------------------------------------------------------------------------------
# Parse command-line arguments.
# ------------------------------------------------------------------------------
COMMAND="dev"
FORCE="false"

for arg in "$@"; do
    case "$arg" in
        dev)
            COMMAND="dev"
            ;;
        prod|--prod|build|standalone)
            COMMAND="prod"
            ;;
        stop)
            COMMAND="stop"
            ;;
        restart)
            COMMAND="restart"
            ;;
        status)
            COMMAND="status"
            ;;
        test)
            COMMAND="test"
            ;;
        -f|--force)
            FORCE="true"
            ;;
        help|--help|-h)
            show_help
            exit 0
            ;;
        *)
            echo -e "${YELLOW}Неизвестный аргумент: $arg${NC}"
            show_help
            exit 1
            ;;
    esac
done

case "$COMMAND" in
    dev)
        start_dev "$FORCE"
        ;;
    prod)
        start_prod "$FORCE"
        ;;
    stop)
        stop_services
        ;;
    restart)
        stop_services
        sleep 1
        start_dev "true"
        ;;
    status)
        check_status
        ;;
    test)
        run_tests
        ;;
esac
