# Native standalone packaging

This directory builds both standalone products as PyInstaller one-directory
packages and owns the maintainer build/release procedure. The root
[`README.md`](../README.md) is the Russian end-user manual.

Build on the target operating system and architecture; PyInstaller does not
cross-compile its embedded Python interpreter. See the upstream
[multi-OS guidance](https://pyinstaller.org/en/stable/usage.html#supporting-multiple-operating-systems).

## Build a package

Use Python 3.13 and Node.js 22.12+ to match the release runners' toolchain family.
Packages embed Python and dependencies but require no installed Python, pip,
Node.js, or source checkout. They contain no office suite or system document
fonts. The canonical version is read from root `VERSION`.

From the repository root on Linux:

```bash
python3 -m venv .venv-release
. .venv-release/bin/activate
python -m pip install -r backend/requirements.txt -r backend/requirements-headless.txt -r release_tools/requirements-build.txt
cd frontend
npm ci
npm run build
cd ..
python release_tools/build_release.py --product headless --output-dir ../report-engine-packages
python release_tools/build_release.py --product web --output-dir ../report-engine-packages
```

On Windows PowerShell, replace the first two commands with:

```powershell
py -3.13 -m venv .venv-release
.\.venv-release\Scripts\Activate.ps1
```

Use the same remaining `python`/`npm` commands on the Windows host. Backend HTTP
requirements are needed for web; the pinned headless requirements provide MCP.
A headless-only build needs no frontend build, but both-product verification
and the current CI matrix build the SPA.

Output directories are `report-engine-<product>-v<version>-<platform>`, with
platform tags `linux-x64` or `windows-x64`. Keep the complete directory, including
`_internal`, when distributing or testing. The builder replaces an existing
output directory with the same package name; use a separate output root when
preserving prior builds. Do not commit generated packages or runtimes.

Headless contains no frontend; web contains the SPA, serves loopback HTTP,
and also exposes live SSE MCP. Web is not a stdio MCP executable.

## Runtime resources and package UX

The builder collects `docx` templates and source directories, JSON Schema data,
LaTeX symbol data, the canonical agent rules, the unchanged default logo, and
`VERSION`. Source directories are needed because python-docx opens templates
through `docx/parts/../templates`. The web package additionally includes every
SPA asset, including KaTeX browser fonts; these are not system document fonts.
Required frozen data is compared byte-for-byte with its inputs before assembly.
The fix protects export paths, not only successful imports or `--help` startup.

Each package receives a Russian quick start and troubleshooting guide rendered
from `package_README.md`. Headless launcher notices use stderr to preserve MCP
stdio. Web launchers print the selected URL and attempt to open the browser
after `/api/health` succeeds. Without browser-opening tools, the server still
runs and the URL can be opened manually. Windows launchers use UTF-8 and pause
on failure; Linux pauses only in an interactive terminal. The direct web
executable prints its URL without opening a browser.

## Verification and native smoke

Install the checked-in test dependencies separately from runtime and PyInstaller
requirements. Both CI workflows use this file; every release job also installs
both product requirement files for the full regression suite and JSON Schema
resource inventory. Run the project gates from the root:

The root `requirements-dev.txt` contains only `pytest` and the HTTP client used by API tests; runtime packages never include it.

```bash
python -m pip install -r requirements-dev.txt
cd frontend
npm test
npm run lint
npm run build
cd ..
python -m pytest -v
python -m pytest tests/test_packaging.py -v
```

The packaging suite uses fixture bundles to reject missing/corrupted DOCX,
schema, math, agent-rule, logo, and web resources. It does not invoke PyInstaller
or substitute for frozen executable export tests. Windows launcher checks on
Linux are static, not Windows runtime verification.

After building both packages, test from a working directory outside the checkout,
using absolute executable/output paths and `REPORT_ENGINE_DISABLE_PDF=1`:

1. **Headless:** connect a real MCP stdio client to the frozen executable with
   `--output-dir` pointing to an existing writable directory. Initialize, discover
   tools/resources, read the rules, create a report, add sections and a formula,
   select the default logo, lint, read fresh revisions, and call `export_report`.
   Also check `import_profile` with a version-1 file and a stale metadata revision.
2. **Web:** start the frozen executable on an explicit free port. Fetch
   `/api/health`, `/api/version`, `/api/capabilities`, `/`, and referenced SPA assets.
   Expect PDF disabled. POST multipart `meta`, `content`, and `format=docx` to
   `/api/generate` using a report with a formula and default logo.
3. **DOCX:** verify both ZIP archives, readable document XML, native `m:oMath`
   content, and embedded default-logo media. An HTTP 200 or an existing filename
   alone is insufficient.
4. **Launcher/connection UX:** run the convenience launchers, confirm the printed
   selected URL and readiness-gated browser opening, then connect live SSE MCP
   from the web modal. Check failure exit codes, Windows UTF-8 paths/error pauses,
   and clean headless protocol stdout on the actual target OS.

Both Linux products have passed frozen DOCX export smoke. Do not equate that
result with Windows, antivirus, or target-machine PDF acceptance; record the
tested platform and remaining limits in [`RELEASE_STATUS.md`](../RELEASE_STATUS.md).

## Maintainer release procedure

1. Select the next SemVer version: breaking contracts require explicit migration
   notes; distinguish features from fixes. `0.1.0` is the prepared first release,
   and the checkout now uses `0.1.0` after the release version bump.
2. Set root `VERSION` to the chosen version. In `frontend/`, run
   `npm version X.Y.Z --no-git-tag-version` to align `package.json` and
   `package-lock.json` without creating a tag. Do not hand-edit API/MCP versions:
   they read `VERSION`.
3. Write concise, user-facing release notes in Russian only. Explain what is new
   for users and what the package contains; do not keep a changelog file in the
   repository and do not maintain an English mirror. For `0.1.0`, introduce the
   product as a first release rather than presenting a changelog-style list.
   Publish the notes on the GitHub Release. Update `RELEASE_STATUS.md` without
   promoting untested platforms/capabilities to verified.
4. Perform the DOX pass, run the gates above, build native packages and run full
   smoke on available target hosts. Record unavailable checks honestly, including
   Windows runtime, target-machine PDF/fonts, and antivirus heuristics.
5. Review and commit only release-related changes with a Conventional Commit.
   Do not include generated artifacts, credentials, or unrelated dirty files.
6. Only on explicit maintainer authorization, publish the prepared commit and
   an annotated matching tag. Example for the first release:

   ```bash
   git tag -a v0.1.0 -m "Release 0.1.0"
   git push origin v0.1.0
   ```

   Ensure the tagged commit is the intended release commit; never move a
   published tag to repair a package.
7. Watch `.github/workflows/standalone-packages.yml`. Its four native jobs
   build headless/web on Ubuntu 22.04 and Windows Server 2022 x64, build the
   frontend, run pytest, enforce tag/`VERSION` equality, assemble packages, run
   frozen `--help`, and upload ZIP artifacts. Its current smoke step does **not**
   execute packaged DOCX export or target-machine PDF conversion.
8. The publish job waits for all builds, downloads the four ZIPs, and attaches
   them to GitHub Release without supplying or generating a release body. Apply
   the curated Russian notes after publication. Confirm product/version/platform
   names and artifact presence; retain the optional-PDF/manual-DOCX fallback and
   disclose remaining verification limits in the release notes.

The CI publication contract is also recorded in
[`.github/AGENTS.md`](../.github/AGENTS.md). Ordinary documentation edits do not
authorize a version bump, tag, or push.

## PDF capability

PDF conversion is not bundled into native releases. Capability checks look for a
working `soffice`/`libreoffice` or ONLYOFFICE Document Builder `docbuilder`
command and expose PDF only when its version probe succeeds.
`REPORT_ENGINE_PDF_CONVERTER` can select a local executable;
`REPORT_ENGINE_DISABLE_PDF=1` disables the capability. Web reports status through
`/api/capabilities`; headless includes PDF in the `export_report` format schema
only when available. Conversion uses removable temporary files.

If no converter is found, export DOCX and convert it manually in Microsoft
Office, LibreOffice, or OnlyOffice. A successful version probe does not prove
conversion or typography: target-machine acceptance needs a working CLI,
compatible fonts, and clean-machine rendering tests. Docker installs an office
converter and fonts during image construction; that is separate from native
package contents and does not establish PDF acceptance for those packages.
