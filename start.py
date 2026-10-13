#!/usr/bin/env python3
"""Launch the GOST 7.32 report constructor across platforms with Python 3."""

import sys
import os
import subprocess
import signal
import time
import shutil
import urllib.request

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")

BACKEND_PORT = 8000
FRONTEND_PORT = 5173

# ANSI colors supported by Linux, macOS, and Windows Terminal.
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner():
    print(f"{CYAN}{BOLD}")
    print("==================================================================")
    print("   Конструктор отчётов по ГОСТ 7.32")
    print("   Генератор и нормоконтроль отчетов по ГОСТ 7.32")
    print("==================================================================")
    print(f"{RESET}")


def show_help():
    print_banner()
    print(f"{BOLD}Использование:{RESET}")
    print("  python start.py [команда]\n")
    print(f"{BOLD}Команды:{RESET}")
    print(f"  {GREEN}dev{RESET} (по умолчанию)  Запуск в режиме разработки (FastAPI :8000 + Vite :5173)")
    print(f"  {GREEN}prod{RESET} | {GREEN}build{RESET}        Сборка фронтенда и запуск единого сервера на :8000")
    print(f"  {YELLOW}stop{RESET}                Остановить запущенные процессы")
    print(f"  {BLUE}status{RESET}              Проверить статус сервисов")
    print(f"  {BLUE}test{RESET}                Запустить тесты (pytest)")
    print(f"  {CYAN}help{RESET}                Показать справку\n")


def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def get_python_exec() -> str:
    venv_py = os.path.join(BACKEND_DIR, "venv", "bin", "python3")
    if os.name == 'nt':
        venv_py = os.path.join(BACKEND_DIR, "venv", "Scripts", "python.exe")
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable


def check_prerequisites():
    print(f"{BLUE}▶ Проверка окружения...{RESET}")
    py_exec = get_python_exec()
    print(f"{GREEN}✓ Python:{RESET} {py_exec}")

    # Locate npm and Node.js.
    node_path = shutil.which("node")
    npm_path = shutil.which("npm")
    if not node_path or not npm_path:
        # Fall back to an nvm-managed installation.
        nvm_dir = os.path.expanduser("~/.nvm/versions/node")
        if os.path.exists(nvm_dir):
            versions = sorted(os.listdir(nvm_dir))
            if versions:
                bin_path = os.path.join(nvm_dir, versions[-1], "bin")
                os.environ["PATH"] = bin_path + os.pathsep + os.environ.get("PATH", "")
                node_path = shutil.which("node")
                npm_path = shutil.which("npm")

    if not node_path or not npm_path:
        print(f"{RED}❌ Node.js или npm не найдены! Установите Node.js (v18+).{RESET}")
        sys.exit(1)

    print(f"{GREEN}✓ Node.js & npm доступны.{RESET}")

    # Install frontend dependencies when node_modules is absent.
    if not os.path.exists(os.path.join(FRONTEND_DIR, "node_modules")):
        print(f"{YELLOW}Установка зависимостей фронтенда (npm install)...{RESET}")
        subprocess.run(["npm", "install"], cwd=FRONTEND_DIR, check=True)

    # Check optional PDF converters without making DOCX startup depend on them.
    converter = shutil.which("libreoffice") or shutil.which("soffice") or shutil.which("docbuilder")
    if converter:
        print(f"{GREEN}✓ PDF-конвертер найден (экспорт в PDF активен).{RESET}")
    else:
        print(f"{YELLOW}⚠️ PDF-конвертер не найден (DOCX доступен, PDF можно получить вручную).{RESET}")


def stop_processes():
    print_banner()
    print(f"{YELLOW}Остановка процессов на портах {BACKEND_PORT} и {FRONTEND_PORT}...{RESET}")
    if os.name != 'nt':
        try:
            subprocess.run(f"lsof -ti :{BACKEND_PORT} :{FRONTEND_PORT} | xargs -r kill -9", shell=True)
        except Exception:
            pass
    print(f"{GREEN}✓ Сервисы остановлены.{RESET}")


def check_status():
    print_banner()
    print(f"{BOLD}Статус сервисов:{RESET}\n")
    b_up = is_port_in_use(BACKEND_PORT)
    f_up = is_port_in_use(FRONTEND_PORT)

    print(f"  • Бэкенд (:{BACKEND_PORT}):  {GREEN + 'запущен' if b_up else RED + 'остановлен'}{RESET}")
    if b_up:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{BACKEND_PORT}/api/health", timeout=2) as r:
                if r.status == 200:
                    print(f"    {GREEN}✓ API (/api/health) отвечает корректно{RESET}")
        except Exception:
            pass

    print(f"  • Фронтенд (:{FRONTEND_PORT}): {GREEN + 'запущен' if f_up else RED + 'остановлен'}{RESET}\n")


def run_tests():
    print_banner()
    py_exec = get_python_exec()
    print(f"{BLUE}▶ Запуск тестов (pytest)...{RESET}\n")
    subprocess.run([py_exec, "-m", "pytest", "tests/", "-v"], cwd=ROOT_DIR)


def start_dev():
    print_banner()
    check_prerequisites()

    if is_port_in_use(BACKEND_PORT):
        print(f"{RED}❌ Порт {BACKEND_PORT} уже занят! Запустите 'python start.py stop' перед стартом.{RESET}")
        sys.exit(1)
    if is_port_in_use(FRONTEND_PORT):
        print(f"{RED}❌ Порт {FRONTEND_PORT} уже занят! Запустите 'python start.py stop' перед стартом.{RESET}")
        sys.exit(1)

    py_exec = get_python_exec()
    print(f"\n{CYAN}Запуск сервисов в режиме разработки (Dev Mode)...{RESET}\n")

    env = os.environ.copy()
    env["FORWARDED_ALLOW_IPS"] = "*"
    backend_proc = subprocess.Popen(
        [py_exec, "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", str(BACKEND_PORT), "--proxy-headers", "--forwarded-allow-ips=*", "--reload"],
        cwd=ROOT_DIR,
        env=env
    )

    frontend_proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", str(FRONTEND_PORT)],
        cwd=FRONTEND_DIR,
        env=env
    )

    time.sleep(2)
    print(f"\n{GREEN}{BOLD}Сервисы запущены.{RESET}")
    print("==================================================================")
    print(f"  {BOLD}Веб-интерфейс:{RESET}      {CYAN}http://localhost:{FRONTEND_PORT}{RESET}")
    print(f"  {BOLD}API Сервер:{RESET}         {CYAN}http://localhost:{BACKEND_PORT}{RESET}")
    print(f"  {BOLD}Swagger документация:{RESET} {CYAN}http://localhost:{BACKEND_PORT}/docs{RESET}")
    print("==================================================================")
    print(f"{YELLOW}Для остановки нажмите {BOLD}Ctrl + C{RESET}\n")

    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None or frontend_proc.poll() is not None:
                break
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Остановка процессов...{RESET}")
    finally:
        for p in [backend_proc, frontend_proc]:
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        print(f"{GREEN}✓ Все процессы остановлены. До свидания!{RESET}")


def start_prod():
    print_banner()
    check_prerequisites()

    if is_port_in_use(BACKEND_PORT):
        print(f"{RED}❌ Порт {BACKEND_PORT} уже занят! Запустите 'python start.py stop' перед стартом.{RESET}")
        sys.exit(1)

    print(f"{BLUE}▶ Сборка React фронтенда (npm run build)...{RESET}")
    subprocess.run(["npm", "run", "build"], cwd=FRONTEND_DIR, check=True)
    print(f"{GREEN}Фронтенд собран в frontend/dist.{RESET}\n")

    py_exec = get_python_exec()
    print(f"\n{GREEN}{BOLD}Сервер запущен в автономном режиме.{RESET}")
    print("==================================================================")
    print(f"  {BOLD}Веб-приложение:{RESET}     {CYAN}http://localhost:{BACKEND_PORT}{RESET}")
    print(f"  {BOLD}API Swagger:{RESET}        {CYAN}http://localhost:{BACKEND_PORT}/docs{RESET}")
    print("==================================================================")
    print(f"{YELLOW}Для остановки нажмите {BOLD}Ctrl + C{RESET}\n")

    try:
        prod_env = os.environ.copy()
        prod_env["FORWARDED_ALLOW_IPS"] = "*"
        subprocess.run(
            [py_exec, "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", str(BACKEND_PORT), "--proxy-headers", "--forwarded-allow-ips=*"],
            cwd=ROOT_DIR,
            env=prod_env
        )
    except KeyboardInterrupt:
        print(f"\n{GREEN}✓ Сервер остановлен.{RESET}")


def main():
    cmd = "dev"
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()

    if cmd in ("dev", "start"):
        start_dev()
    elif cmd in ("prod", "build", "standalone", "--prod"):
        start_prod()
    elif cmd in ("stop", "kill"):
        stop_processes()
    elif cmd in ("status", "check"):
        check_status()
    elif cmd in ("test", "pytest"):
        run_tests()
    elif cmd in ("help", "--help", "-h"):
        show_help()
    else:
        print(f"{YELLOW}Неизвестная команда: {cmd}{RESET}")
        show_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
