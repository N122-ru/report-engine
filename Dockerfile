FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    FORWARDED_ALLOW_IPS=*

# Установка LibreOffice для headless-конвертации и русских ГОСТ шрифтов
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    libreoffice-calc \
    fonts-liberation \
    fonts-dejavu-core \
    fontconfig \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Шрифты Microsoft (прежде всего Times New Roman — единственный шрифт документа по ГОСТ 7.32).
# Пакет живёт в contrib; EULA принимаем автоматически.
# Fallback осознанный: если SourceForge недоступен — сборка не падает,
# остаёмся на метрически совместимых Liberation/DejaVu (см. WARNING в логе).
RUN set -x; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's/Components: main$/Components: main contrib/' /etc/apt/sources.list.d/debian.sources; \
      sed -i 's/Components: main /Components: main contrib /' /etc/apt/sources.list.d/debian.sources; \
    else \
      printf 'deb http://deb.debian.org/debian bookworm contrib\n' >> /etc/apt/sources.list; \
    fi; \
    (apt-get update \
      && echo ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true | debconf-set-selections \
      && apt-get install -y --no-install-recommends ttf-mscorefonts-installer) \
    || echo "WARNING: msttcorefonts не установились — PDF соберётся с подменой (Liberation/DejaVu)"; \
    fc-cache -f || true; \
    fc-match "Times New Roman" || true; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Canonical product version used by the API and MCP handshake.
COPY VERSION ./VERSION

# Установка Python-зависимостей
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# Копирование исходного кода бэкенда и ассетов
COPY backend/ ./backend/
COPY assets/ ./assets/

# Копирование готовой статической сборки фронтенда (React SPA)
COPY frontend/dist ./frontend/dist

# Порт сервиса
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

# Запуск единого сервиса (FastAPI + SPA) с поддержкой проксирования
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
