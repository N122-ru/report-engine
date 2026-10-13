import os
import shutil
import subprocess

import pytest

from backend.app.version import APP_VERSION
from release_tools import build_release as packaging
from release_tools.build_release import (
    _assemble_package,
    _build_binary,
    _pyinstaller_command,
    _required_runtime_data,
    _verify_bundle_data,
    distribution_name,
    platform_tag,
)


@pytest.fixture(autouse=True)
def frontend_build(tmp_path, monkeypatch):
    """Keep packaging unit tests independent of a prior Node.js build."""
    dist = tmp_path / "frontend/dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    (dist / "assets/app.js").write_text("console.log('fixture');", encoding="utf-8")
    (dist / "assets/font.woff2").write_bytes(b"font fixture")
    monkeypatch.setattr(packaging, "FRONTEND_DIST", dist)


@pytest.fixture
def frozen_bundle(tmp_path):
    """Mirror the required data layout without invoking the native compiler."""
    bundle = tmp_path / "bundle"
    for source, relative in _required_runtime_data("web"):
        target = bundle / "_internal" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return bundle


@pytest.mark.parametrize("product", ["headless", "web"])
def test_pyinstaller_collects_docx_templates_and_runtime_assets(product, tmp_path):
    command = _pyinstaller_command(product, tmp_path, tmp_path, tmp_path)
    assert command[command.index("--collect-all") + 1] == "docx"
    assert command[command.index("--collect-data") + 1] == "jsonschema_specifications"
    assert command[command.index("--contents-directory") + 1] == "_internal"
    additions = [command[index + 1] for index, arg in enumerate(command) if arg == "--add-data"]
    assert any("default_logo.png" in value for value in additions)
    required = {relative.as_posix() for _, relative in _required_runtime_data(product)}
    assert {
        "docx/parts/__init__.py",
        "docx/templates/default.docx", "docx/templates/default-footer.xml",
        "docx/templates/default-header.xml", "docx/templates/default-styles.xml",
        "docx/templates/default-settings.xml", "docx/templates/default-comments.xml",
        "assets/SKILL.md", "assets/default_logo.png", "VERSION",
        "latex2mathml/unimathsymbols.txt",
        "jsonschema_specifications/schemas/draft202012/metaschema.json",
    } <= required
    assert ("frontend/dist/index.html" in required) == (product == "web")


@pytest.mark.parametrize("product", ["headless", "web"])
def test_complete_frozen_bundle_passes_data_verification(product, frozen_bundle):
    _verify_bundle_data(frozen_bundle, product)


@pytest.mark.parametrize("relative", [
    "docx/parts/__init__.py",
    "docx/templates/default.docx", "docx/templates/default-footer.xml",
    "docx/templates/default-header.xml", "docx/templates/default-styles.xml",
    "docx/templates/default-settings.xml", "docx/templates/default-comments.xml",
    "assets/SKILL.md", "assets/default_logo.png", "VERSION",
    "latex2mathml/unimathsymbols.txt", "frontend/dist/index.html",
    "jsonschema_specifications/schemas/draft202012/metaschema.json",
])
def test_incomplete_frozen_bundle_is_rejected(relative, frozen_bundle):
    (frozen_bundle / "_internal" / relative).unlink()
    with pytest.raises(RuntimeError, match="Required bundled data"):
        _verify_bundle_data(frozen_bundle, "web")


def test_corrupted_frozen_bundle_is_rejected(frozen_bundle):
    (frozen_bundle / "_internal/assets/SKILL.md").write_text("truncated", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Bundled data differs"):
        _verify_bundle_data(frozen_bundle, "headless")


def test_web_bundle_verifies_every_frontend_asset(frozen_bundle):
    asset = next((frozen_bundle / "_internal/frontend/dist/assets").iterdir())
    asset.unlink()
    with pytest.raises(RuntimeError, match="Required bundled data"):
        _verify_bundle_data(frozen_bundle, "web")


@pytest.mark.parametrize("product", ["headless", "web"])
def test_build_rejects_frozen_output_without_docx_footer(product, frozen_bundle, tmp_path, monkeypatch):
    staging = tmp_path / "staging"

    def compile_incomplete_bundle(*args, **kwargs):
        target = staging / "dist" / f"report-engine-{product}"
        shutil.copytree(frozen_bundle, target)
        (target / "_internal/docx/templates/default-footer.xml").unlink()

    monkeypatch.setattr(packaging.subprocess, "run", compile_incomplete_bundle)
    with pytest.raises(RuntimeError, match="Required bundled data"):
        _build_binary(product, staging)


@pytest.mark.parametrize("product", ["headless", "web"])
def test_distribution_name_contains_product_version_and_platform(product):
    assert distribution_name(product) == f"report-engine-{product}-v{APP_VERSION}-{platform_tag()}"


def test_unknown_product_is_rejected():
    with pytest.raises(ValueError, match="Unknown product"):
        distribution_name("unknown")


@pytest.mark.parametrize("product", ["headless", "web"])
def test_package_assembly_contains_no_office_runtime(product, tmp_path):
    built = tmp_path / "built"
    built.mkdir()
    (built / f"report-engine-{product}").write_text("binary", encoding="utf-8")

    package = _assemble_package(built, tmp_path / "release", product)

    manifest = (package / "PACKAGE-MANIFEST.json").read_text(encoding="utf-8")
    assert f'"version": "{APP_VERSION}"' in manifest
    assert '"profile"' not in manifest
    assert "no-pdf" not in package.name
    assert "LibreOffice" in (package / "README.md").read_text(encoding="utf-8")
    assert (package / "PACKAGE-MANIFEST.json").is_file()
    assert not (package / "runtime").exists()
    assert not (package / "runtime/fonts").exists()


@pytest.mark.parametrize("product", ["headless", "web"])
def test_package_guide_contains_first_run_mcp_and_troubleshooting(product, tmp_path):
    built = tmp_path / "built"
    built.mkdir()
    package = _assemble_package(built, tmp_path / "release", product)
    guide = (package / "README.md").read_text(encoding="utf-8")
    for text in ("Перед первым запуском", "stdio", "SSE", "ИИ-агент (MCP)", "Команда агенту",
                 "--output-dir", "Устранение неполадок", "_internal", "Ctrl+C", "--port 8001"):
        assert text in guide
    assert f"В этом пакете находится только **{product}**" in guide
    assert APP_VERSION in guide
    assert "@PRODUCT@" not in guide and "@VERSION@" not in guide and "@PLATFORM@" not in guide


@pytest.mark.parametrize("product", ["headless", "web"])
def test_windows_launchers_preserve_utf8_paths_and_pause_on_failure(product):
    launcher = (packaging.TOOLS_ROOT / f"launchers/start-{product}.bat").read_text(encoding="utf-8")
    assert "chcp 65001 >nul" in launcher
    assert "%~dp0" in launcher
    assert f'"%ROOT_DIR%report-engine-{product}.exe"' in launcher
    assert "%*" in launcher
    assert "pause" in launcher and "Не удалось" in launcher
    assert "README.md" in launcher
    if product == "headless":
        for line in launcher.splitlines():
            if line.startswith("echo "):
                assert "1>&2" in line
        assert "stdio" in launcher
    else:
        assert 'start "" "http://127.0.0.1:%REPORT_ENGINE_BROWSER_PORT%"' in launcher
        assert "/api/health" in launcher
        assert "--port=" in launcher


@pytest.fixture
def launcher_package(tmp_path):
    """Exercise launcher quoting outside the source tree and from another cwd."""
    package = tmp_path / "package with spaces"
    package.mkdir()
    for product in ("headless", "web"):
        shutil.copy2(packaging.TOOLS_ROOT / f"launchers/start-{product}.sh", package)
    return package


def write_executable(path, body):
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


@pytest.mark.skipif(os.name != "posix", reason="Linux shell launcher runtime test")
def test_headless_launcher_notices_never_pollute_mcp_stdout(launcher_package, tmp_path):
    write_executable(launcher_package / "report-engine-headless", 'printf "%s\\n" "$@" > "$ARG_LOG"\ncat\n')
    log = tmp_path / "args.txt"
    result = subprocess.run(
        ["bash", str(launcher_package / "start-headless.sh")], cwd=tmp_path,
        input='{"jsonrpc":"2.0"}\n', text=True, capture_output=True, timeout=5,
        env=dict(os.environ, ARG_LOG=str(log)),
    )
    assert result.returncode == 0
    assert result.stdout == '{"jsonrpc":"2.0"}\n'
    assert "MCP-клиент" in result.stderr and "README.md" in result.stderr
    assert log.read_text().splitlines() == ["--output-dir", str(launcher_package / "output")]
    assert (launcher_package / "output").is_dir()


@pytest.mark.skipif(os.name != "posix", reason="Linux shell launcher runtime test")
@pytest.mark.parametrize("product", ["headless", "web"])
def test_linux_launcher_explains_failure_and_preserves_exit_code(product, launcher_package, tmp_path):
    write_executable(launcher_package / f"report-engine-{product}", "exit 7\n")
    result = subprocess.run(
        ["bash", str(launcher_package / f"start-{product}.sh")], cwd=tmp_path,
        text=True, capture_output=True, input="", timeout=5,
        env=dict(os.environ, DISPLAY="", WAYLAND_DISPLAY=""),
    )
    assert result.returncode == 7
    assert "Не удалось" in result.stderr and "README.md" in result.stderr


@pytest.mark.skipif(os.name != "posix", reason="Linux shell launcher runtime test")
@pytest.mark.parametrize("arguments", [["--port", "8123"], ["--port=8123"]])
def test_linux_web_launcher_opens_selected_url_only_after_readiness(arguments, launcher_package, tmp_path):
    write_executable(launcher_package / "report-engine-web", 'sleep 0.5\ntouch "$READY_FILE"\nsleep 1\n')
    write_executable(launcher_package / "curl", 'test -f "$READY_FILE"\n')
    write_executable(launcher_package / "xdg-open", 'test -f "$READY_FILE" || exit 1\nprintf "%s" "$1" > "$URL_LOG"\n')
    log = tmp_path / "opened-url.txt"
    result = subprocess.run(
        ["bash", str(launcher_package / "start-web.sh"), *arguments], cwd=tmp_path,
        text=True, capture_output=True, input="", timeout=5,
        env=dict(os.environ, DISPLAY=":0", READY_FILE=str(tmp_path / "ready"), URL_LOG=str(log),
                 PATH=str(launcher_package) + os.pathsep + os.environ["PATH"]),
    )
    assert result.returncode == 0, result.stderr
    assert "http://127.0.0.1:8123" in result.stdout
    assert log.read_text() == "http://127.0.0.1:8123"
