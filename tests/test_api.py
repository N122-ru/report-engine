import sys, os
sys.path.insert(0, os.path.abspath("backend"))

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["service"] == "Report Engine"

def test_generate_docx():
    import json
    meta = {
        "university": "Тестовый технический университет",
        "institute": "Институт информационных технологий",
        "department": "Кафедра информационных систем",
        "work_number": 1,
        "work_theme": "Тестовая лаба",
        "discipline": "Физика",
        "students": [{"fio": "И.И. Иванов", "group": "ИВТ-101"}],
        "teachers": [{"fio": "П.П. Петров", "role": "доцент"}]
    }
    content = "# Цель работы\nТестовая цель работы.\n\n# Ход работы\nТестовый ход работы.\n\n# Вывод\nТестовый вывод."

    res = client.post(
        "/api/generate",
        data={
            "meta": json.dumps(meta),
            "content": content,
            "format": "docx"
        }
    )
    assert res.status_code == 200
    assert len(res.content) > 10000
    assert res.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    with open("test_output.docx", "wb") as f:
        f.write(res.content)


def test_generate_rejects_invalid_image_bytes():
    import json

    response = client.post(
        "/api/generate",
        data={"meta": json.dumps({"work_number": 1}), "content": "Текст."},
        files={"images": ("broken.png", b"not an image", "image/png")},
    )

    assert response.status_code == 400
    assert "поддерживаемое изображение" in response.json()["detail"]

def test_autofix():
    bad_md = '# 1. Цель работы.\n\n![Схема сети - тестовая.](net.png)\n\n```python\nmsg = "hello - world"\nval = x - y\n```\n\n\n\n\n# 2. Выводы.'
    res = client.post("/api/autofix", data={"content": bad_md})
    assert res.status_code == 200
    data = res.json()
    assert "# 1. Цель работы" in data["fixed_content"] # dot stripped
    assert "–" in data["fixed_content"] or "—" in data["fixed_content"] # hyphen converted to dash
    # Preserve straight quotes and hyphens inside fenced code.
    assert 'msg = "hello - world"' in data["fixed_content"]
    assert 'val = x - y' in data["fixed_content"]

@pytest.mark.parametrize("literal", [
    '`print("value") ** * \'word\' \\n`',
    '``print(`"value"`) ** * \'word\' \\n``',
    '```inline `"value"` and ``nested`````',
])
def test_autofix_preserves_literal_code_spans_and_is_idempotent(literal):
    content = f'Получено "значение": {literal}. Проза - описание.'
    response = client.post("/api/autofix", data={"content": content})
    assert response.status_code == 200
    fixed = response.json()["fixed_content"]
    assert literal in fixed
    assert '«значение»' in fixed
    assert 'Проза\u00a0— описание.' in fixed
    second = client.post("/api/autofix", data={"content": fixed}).json()
    assert second["fixed_content"] == fixed

def test_verify_endpoint():
    if not os.path.exists("test_output.docx"):
        test_generate_docx()
    with open("test_output.docx", "rb") as f:
        res = client.post("/api/verify", files={"file": ("test_output.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert res.status_code == 200
    data = res.json()
    assert data["is_valid"] is True
    assert data["score"] == 100
    assert len(data["errors"]) == 0
    if os.path.exists("test_output.docx"):
        os.remove("test_output.docx")

def test_generate_bad_options_422():
    import json
    meta = {"work_number": 1, "work_theme": "T", "discipline": "D"}
    res = client.post(
        "/api/generate",
        data={"meta": json.dumps(meta), "content": "x", "format": "docx", "options": "not-json"}
    )
    assert res.status_code == 422

def test_generate_bad_format_400():
    import json
    res = client.post(
        "/api/generate",
        data={"meta": json.dumps({"work_number": 1}), "content": "x", "format": "exe"}
    )
    assert res.status_code == 400

def test_verify_reference_warning():
    # A figure without a prose reference or attachment triggers REFERENCE
    # and IMAGES warnings, yielding a score of 92.
    content = "# Цель работы\nТекст без упоминаний.\n\n# Ход работы\nРабота.\n\n# Вывод\nИтог.\n\n![Схема сети](net.png)\n"
    res = client.post(
        "/api/generate",
        data={"meta": "{}", "content": content, "format": "docx"}
    )
    assert res.status_code == 200
    res = client.post("/api/verify", files={"file": ("r.docx", res.content)})
    assert res.status_code == 200
    data = res.json()
    assert any(w["type"] == "REFERENCE" for w in data["warnings"])
    assert any(w["type"] == "IMAGES" for w in data["warnings"])
    assert data["score"] == 92

def test_autofix_table_cells():
    content = "| Параметр | Значение |\n|---|---|\n| скорость за 2026 г. | тест - тест |"
    res = client.post("/api/autofix", data={"content": content})
    assert res.status_code == 200
    fixed = res.json()["fixed_content"]
    assert "за 2026 г." not in fixed  # Ordinary spaces become nonbreaking spaces.
    assert res.json()["fixes_applied"]  # Include the fix in the response.
    assert "|" in fixed and "---" in fixed  # Preserve table structure.

def test_autofix_deduplicates_figure_captions():
    # Verify duplicate figure-caption removal in /api/autofix.
    content = "![Схема сети](net.png)\nРисунок 1 — Схема сети"
    res = client.post("/api/autofix", data={"content": content})
    assert res.status_code == 200
    fixed = res.json()["fixed_content"]
    assert "Рисунок 1 — Схема сети" not in fixed
    assert "![Схема сети](net.png)" in fixed
    assert any("дублирующая подпись" in fix.lower() for fix in res.json()["fixes_applied"])

    # Replace a filename alt with the meaningful duplicate caption.
    content2 = "![image.png](image.png)\n\nРисунок 2 — Архитектура комплекса"
    res2 = client.post("/api/autofix", data={"content": content2})
    assert res2.status_code == 200
    fixed2 = res2.json()["fixed_content"]
    assert "![Архитектура комплекса](image.png)" in fixed2
    assert "Рисунок 2 —" not in fixed2

    # Preserve ordinary prose following an image.
    content3 = "![Топология](net.png)\n\nРисунок 1. В соответствии со схемой выполним настройку интерфейса."
    res3 = client.post("/api/autofix", data={"content": content3})
    assert res3.status_code == 200
    fixed3 = res3.json()["fixed_content"]
    assert "В соответствии со схемой выполним настройку интерфейса." in fixed3.replace("\xa0", " ")
    assert not any("дублирующая подпись" in fix.lower() for fix in res3.json()["fixes_applied"])

    # Convert the assignment heading to prose.
    content4 = "# Цель работы\nИзучение сети.\n\n# Задание\n1. Настроить адаптер.\n\n# Ход работы\n"
    res4 = client.post("/api/autofix", data={"content": content4})
    assert res4.status_code == 200
    fixed4 = res4.json()["fixed_content"]
    assert "# Задание" not in fixed4
    assert "Для достижения цели поставлены задачи:" in fixed4.replace("\xa0", " ")

def test_spa_index_html_not_cached():
    # Serve index.html with no-store to avoid pinning stale bundles.
    res = client.get("/some-frontend-route")
    assert res.status_code == 200
    assert res.headers.get("cache-control") == "no-store"

def test_spa_path_traversal_prevention():
    # The SPA route must not expose backend source files.
    res = client.get("/../../backend/app/main.py")
    assert "FastAPI Application" not in res.text
    # Unknown SPA paths fall back to index.html.
    assert res.status_code == 200
    assert "<!doctype html>" in res.text or "<div id=\"root\">" in res.text

def test_autofix_idempotent():
    # Repeated clean-text passes must not alternate ordinary spaces and NBSPs.
    for md in ("Таблица 1 - Данные.", "![Рисунок 1 - Схема](a.png)", "Текст - с тире."):
        once = client.post("/api/autofix", data={"content": md}).json()["fixed_content"]
        twice = client.post("/api/autofix", data={"content": once}).json()
        assert twice["fixes_applied"] == []

def test_security_headers():
    res = client.get("/api/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "SAMEORIGIN"
    assert res.headers["referrer-policy"] == "strict-origin-when-cross-origin"

@pytest.mark.anyio
async def test_rate_limiter_unit():
    from app.engine.security import SimpleRateLimiter
    limiter = SimpleRateLimiter()
    test_ip = "192.168.1.100"
    assert await limiter.is_allowed(test_ip, max_requests=2, window_seconds=10) is True
    assert await limiter.is_allowed(test_ip, max_requests=2, window_seconds=10) is True
    assert await limiter.is_allowed(test_ip, max_requests=2, window_seconds=10) is False

def test_rate_limit_endpoint_blocks():
    # Verify that the endpoint blocks a client exceeding the per-IP limit.
    headers = {"X-Forwarded-For": "203.0.113.195"}
    # Autofix allows 45 requests/minute; seed the limiter directly to avoid
    # making 46 HTTP requests.
    from app.engine.security import rate_limiter
    import asyncio
    for _ in range(45):
        asyncio.run(rate_limiter.is_allowed("203.0.113.195", max_requests=45, window_seconds=60))
    # The 46th request must return HTTP 429.
    res = client.post("/api/autofix", data={"content": "тест"}, headers=headers)
    assert res.status_code == 429
    assert "Retry-After" in res.headers

def test_generate_markdown_size_limit_413():
    # Exceed 500 KB but stay below 1024 KB to exercise endpoint validation.
    huge_content = "A" * (600 * 1024)
    res = client.post(
        "/api/generate",
        data={"meta": "{}", "content": huge_content, "format": "docx"}
    )
    assert res.status_code == 413
    assert "500 КБ" in res.json()["detail"]

def test_generate_too_many_images_400():
    # Exceed the 150-image limit.
    files = [("images", (f"img_{i}.png", b"fake", "image/png")) for i in range(151)]
    res = client.post(
        "/api/generate",
        data={"meta": "{}", "content": "тест", "format": "docx"},
        files=files
    )
    assert res.status_code == 400
    assert "максимальное количество" in res.json()["detail"]


def test_image_limits_are_shared_between_http_sessions_and_headless():
    from app.engine.security import MAX_IMAGE_SIZE as http_limit
    from app.engine.sessions import MAX_IMAGE_SIZE as session_limit
    from backend.app.engine.headless_report import MAX_IMAGE_SIZE as headless_limit

    assert http_limit == session_limit == headless_limit == 15 * 1024 * 1024


def test_generate_image_size_error_uses_actual_limit():
    from app.engine.security import MAX_IMAGE_SIZE

    response = client.post("/api/generate", data={"meta": "{}", "content": "Текст"}, files={
        "images": ("screen.png", b"x" * (MAX_IMAGE_SIZE + 1), "image/png"),
    })
    assert response.status_code == 413
    assert response.json()["detail"] == f"Размер файла «screen.png» превышает лимит {MAX_IMAGE_SIZE // (1024 * 1024)} МБ"


def test_verify_docx_size_error_uses_separate_actual_limit():
    from app.engine.security import MAX_VERIFY_SIZE

    response = client.post("/api/verify", files={"file": ("report.docx", b"x" * (MAX_VERIFY_SIZE + 1))})
    assert response.status_code == 413
    assert response.json()["detail"] == f"Размер файла превышает лимит {MAX_VERIFY_SIZE // (1024 * 1024)} МБ"

def test_autofix_size_limit_413():
    huge_content = "A" * (600 * 1024)
    res = client.post("/api/autofix", data={"content": huge_content})
    assert res.status_code == 413
    assert "500 КБ" in res.json()["detail"]

def test_multipart_starlette_size_limit_400():
    # Starlette's ASGI parser rejects text over 1024 KB to prevent ReDoS/OOM.
    huge_content = "A" * (1200 * 1024)
    res = client.post("/api/autofix", data={"content": huge_content})
    assert res.status_code == 400
    assert "exceeded maximum size" in res.json()["detail"]

def test_autofix_simplifies_robotic_status():
    text_with_cliche = (
        "- Адаптер «Беспроводная сеть»: находится в активном состоянии и обеспечивает доступ к сети Интернет;\n"
        "- Адаптер «Сетевое подключение Bluetooth»: среда передачи недоступна."
    )
    res = client.post("/api/autofix", data={"content": text_with_cliche})
    assert res.status_code == 200
    fixed = res.json()["fixed_content"]
    assert "активен, обеспечивает" in fixed
    assert "среда передачи недоступна" in fixed
    assert any("состояния" in fix for fix in res.json()["fixes_applied"])
