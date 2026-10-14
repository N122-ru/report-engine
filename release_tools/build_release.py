"""Build native packages for the standalone headless and web products.

PyInstaller must run on the operating system and architecture that will run the
resulting package. PDF conversion is intentionally a runtime capability: the
package never bundles an office suite or system document fonts.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "release_tools"
SKILL_FILE = ROOT / "assets" / "SKILL.md"
REFERENCE_DIR = ROOT / "assets" / "reference"
REFERENCE_NAMES = ("figures", "formulas", "tables", "style", "literals")
LOGO_FILE = ROOT / "assets" / "default_logo.png"
FRONTEND_DIST = ROOT / "frontend" / "dist"
LATEX_DATA_PACKAGE = "latex2mathml"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.version import APP_VERSION


PRODUCTS = {
    "headless": {
        "entrypoint": TOOLS_ROOT / "entrypoints" / "headless.py",
        "frontend": False,
    },
    "web": {
        "entrypoint": TOOLS_ROOT / "entrypoints" / "web.py",
        "frontend": True,
    },
}


def platform_tag() -> str:
    system = platform.system().casefold()
    system_tag = {"windows": "windows", "linux": "linux"}.get(system, system)
    machine = platform.machine().casefold()
    architecture = {
        "amd64": "x64",
        "x86_64": "x64",
        "x64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine, machine or "unknown")
    return f"{system_tag}-{architecture}"


def distribution_name(product: str, version: str = APP_VERSION) -> str:
    if product not in PRODUCTS:
        raise ValueError(f"Unknown product: {product}")
    return f"report-engine-{product}-v{version}-{platform_tag()}"


def _require_file(path: Path, description: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"Required {description} was not found: {path}")


def _data_argument(source: Path, destination: str) -> str:
    return f"{source}{os.pathsep}{destination}"


def _latex_symbols_file() -> Path:
    try:
        import latex2mathml
    except ImportError as exc:
        raise RuntimeError("latex2mathml must be installed before building a release") from exc
    symbols = Path(latex2mathml.__file__).resolve().with_name("unimathsymbols.txt")
    _require_file(symbols, "latex2mathml symbol data")
    return symbols


def _required_runtime_data(product: str) -> list[tuple[Path, Path]]:
    """Inventory runtime resources independently of PyInstaller's collection rules."""
    data = [
        (SKILL_FILE, Path("assets/SKILL.md")),
        (LOGO_FILE, Path("assets/default_logo.png")),
        (ROOT / "VERSION", Path("VERSION")),
        (_latex_symbols_file(), Path(LATEX_DATA_PACKAGE) / "unimathsymbols.txt"),
    ]
    data.extend((REFERENCE_DIR / f"{name}.md", Path(f"assets/reference/{name}.md"))
                for name in REFERENCE_NAMES)
    for package, directory in (("docx", "templates"), ("jsonschema_specifications", "schemas")):
        module = importlib.import_module(package)
        package_root = Path(module.__file__).resolve().parent
        files = sorted(path for path in (package_root / directory).rglob("*") if path.is_file())
        if not files:
            raise RuntimeError(f"Required {package} {directory} data was not found")
        data.extend((path, Path(package) / path.relative_to(package_root)) for path in files)
        if package == "docx":
            # Template paths traverse parts/../templates, which requires a physical parts directory.
            data.append((package_root / "parts/__init__.py", Path("docx/parts/__init__.py")))
    if PRODUCTS[product]["frontend"]:
        _require_file(FRONTEND_DIST / "index.html", "frontend build")
        data.extend(
            (path, Path("frontend/dist") / path.relative_to(FRONTEND_DIST))
            for path in sorted(FRONTEND_DIST.rglob("*")) if path.is_file()
        )
    for source, _ in data:
        _require_file(source, "runtime data")
    return data


def _verify_bundle_data(built_dir: Path, product: str) -> None:
    """Reject incomplete or altered onedir data before publishing a package."""
    for source, relative in _required_runtime_data(product):
        bundled = built_dir / "_internal" / relative
        _require_file(bundled, "bundled data")
        if bundled.read_bytes() != source.read_bytes():
            raise RuntimeError(f"Bundled data differs from its source: {relative}")


def _pyinstaller_command(
    product: str,
    dist_path: Path,
    work_path: Path,
    spec_path: Path,
) -> list[str]:
    config = PRODUCTS[product]
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--contents-directory",
        "_internal",
        "--collect-all",
        "docx",
        "--collect-data",
        "jsonschema_specifications",
        "--name",
        f"report-engine-{product}",
        "--distpath",
        str(dist_path),
        "--workpath",
        str(work_path),
        "--specpath",
        str(spec_path),
        "--paths",
        str(ROOT),
        "--add-data",
        _data_argument(SKILL_FILE, "assets"),
        "--add-data",
        _data_argument(REFERENCE_DIR, "assets/reference"),
        "--add-data",
        _data_argument(LOGO_FILE, "assets"),
        "--add-data",
        _data_argument(ROOT / "VERSION", "."),
        "--add-data",
        _data_argument(_latex_symbols_file(), LATEX_DATA_PACKAGE),
        "--runtime-hook",
        str(TOOLS_ROOT / "runtime_hooks" / "set_runtime_dir.py"),
    ]
    if config["frontend"]:
        command.extend([
            "--add-data",
            _data_argument(FRONTEND_DIST, "frontend/dist"),
        ])
    command.append(str(config["entrypoint"]))
    return command


def _build_binary(product: str, staging_dir: Path) -> Path:
    dist_path = staging_dir / "dist"
    work_path = staging_dir / "work"
    spec_path = staging_dir / "spec"
    for path in (dist_path, work_path, spec_path):
        path.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        _pyinstaller_command(product, dist_path, work_path, spec_path),
        cwd=ROOT,
        check=True,
    )
    executable_dir = dist_path / f"report-engine-{product}"
    if not executable_dir.is_dir():
        raise RuntimeError(f"PyInstaller did not produce {executable_dir}")
    _verify_bundle_data(executable_dir, product)
    return executable_dir


def _copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _write_package_readme(destination: Path, product: str, version: str) -> None:
    """Render the novice-oriented guide shipped alongside the executable."""
    text = (TOOLS_ROOT / "package_README.md").read_text(encoding="utf-8")
    for marker, value in (("@PRODUCT@", product), ("@VERSION@", version), ("@PLATFORM@", platform_tag())):
        text = text.replace(marker, value)
    (destination / "README.md").write_text(text, encoding="utf-8")


def _assemble_package(built_dir: Path, output_dir: Path, product: str, version: str = APP_VERSION) -> Path:
    package_dir = output_dir / distribution_name(product, version)
    if package_dir.exists():
        shutil.rmtree(package_dir)
    _copy_tree(built_dir, package_dir)

    launcher_suffix = ".bat" if platform.system().casefold() == "windows" else ".sh"
    launcher_name = f"start-{product}{launcher_suffix}"
    shutil.copy2(TOOLS_ROOT / "launchers" / launcher_name, package_dir / launcher_name)
    if launcher_suffix == ".sh":
        launcher = package_dir / launcher_name
        launcher.chmod(launcher.stat().st_mode | 0o111)
        executable_name = f"report-engine-{product}"
    else:
        executable_name = f"report-engine-{product}.exe"

    manifest = {
        "product": product,
        "version": version,
        "platform": platform_tag(),
        "python": platform.python_version(),
        "executable": executable_name,
        "pdf_export": "runtime-detected",
        "frontend_bundled": PRODUCTS[product]["frontend"],
        "converter_bundled": False,
        "fonts_bundled": False,
    }
    (package_dir / "PACKAGE-MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_package_readme(package_dir, product, version)
    if product == "headless":
        (package_dir / "output").mkdir()
    return package_dir


def build_release(product: str, output_dir: Path) -> Path:
    if product not in PRODUCTS:
        raise ValueError(f"Unknown product: {product}")
    config = PRODUCTS[product]
    _require_file(config["entrypoint"], f"{product} entry point")
    _require_file(ROOT / "VERSION", "canonical version file")
    _require_file(TOOLS_ROOT / "runtime_hooks" / "set_runtime_dir.py", "runtime hook")
    _require_file(SKILL_FILE, "agent rules")
    _required_runtime_data(product)

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="report-engine-build-", dir=output_dir) as temp:
        built_dir = _build_binary(product, Path(temp))
        return _assemble_package(built_dir, output_dir, product)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a native standalone Report Engine package")
    parser.add_argument("--product", choices=tuple(PRODUCTS), required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "release")
    args = parser.parse_args()
    try:
        package = build_release(args.product, args.output_dir)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(package)


if __name__ == "__main__":
    main()
