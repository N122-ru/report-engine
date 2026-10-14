# Release Tools AGENTS.md

## Purpose

Own native standalone release assembly for the headless and web products.

## Ownership

- `build_release.py` invokes PyInstaller on the current host and assembles a versioned onedir package.
- `entrypoints/`, `launchers/`, and `runtime_hooks/` define frozen-process startup behavior.
- `README.md` owns English native build commands, smoke checks, package/PDF contracts, and the maintainer version-bump/release procedure.
- `package_README.md` is the Russian novice guide rendered into each package's `README.md`.

## Local Contracts

- Build natively on the target operating system and architecture; never claim cross-platform output from one PyInstaller run.
- Release packages must not copy LibreOffice, OnlyOffice, or system fonts for document rendering; the absence of these files is documented in each package. The web SPA retains its bundled KaTeX browser fonts.
- PDF is a runtime capability detected by the application; missing converters must leave DOCX export available.
- Bundle all `docx/templates` and JSON Schema resources, `latex2mathml/unimathsymbols.txt`, `assets/SKILL.md`, all five `assets/reference/*.md` domain files, `assets/default_logo.png`, and `VERSION`; the web product additionally requires every file in `frontend/dist`.
- The independent required-data inventory must name each reference file and reject missing/corrupted frozen copies for both products; bundle `assets/reference/` explicitly with PyInstaller.
- Verify required frozen `_internal` data byte-for-byte against build inputs before package assembly. Do not depend only on PyInstaller import discovery for package data.
- Collect `docx` sources as well as templates: runtime paths traverse `docx/parts/../templates`, so the physical `parts` directory must survive packaging.
- Do not place generated packages, binaries, or vendor runtimes in the repository.

## Work Guidance

- Keep launchers independent of the source checkout and resolve paths relative to the package directory.
- Keep end-user package instructions in Russian; build code and developer documentation remain English.
- Keep release instructions aligned with `.github/AGENTS.md` and the actual workflow; distinguish CI executable `--help` checks from full native DOCX export smoke.
- Headless launcher notices go to stderr, never MCP stdout. Launch failures preserve the exit code and explain recovery; Windows pauses, while Linux pauses only in an interactive terminal.
- Web launchers print the selected loopback URL and attempt browser opening only after health readiness; missing desktop tools must not prevent server startup.
- Branding and top-level product documentation are separate release phases, not part of a packaging fix.

## Verification

- Run the frontend build followed by `python3 -m pytest -v`.
- Build both native packages and run headless MCP initialize/create/export and web health/capabilities/generate/SPA smoke tests from outside the checkout when PyInstaller is available. Validate generated DOCX archives, native formulas, and the bundled logo.
- Run `python3 -m pytest tests/test_packaging.py -v` for resource completeness, launcher behavior, and package-guide coverage. Windows launcher checks on Linux are static only.

## Child DOX Index

No nested documents.
