# Report Engine: Current Product Contracts

## Scope

Report Engine prepares, edits, checks, and exports academic reports using GOST
7.32-2017 and GOST 2.105-2019 formatting, with bibliography support based on
GOST R 7.0.5. It implements specific checks, not certification of complete
standards compliance or institution-specific requirements.

- Work types include laboratory (ЛР), practical (ПР), calculation/graphic (РГР),
  course papers (КР), course projects (КП), research (НИР), assessment work,
  and educational, industrial, and pre-graduation placements. Custom types are allowed.
- Institutions and personal requisites are user inputs. The bundled SamGTU logo
  is optional; web supports a custom logo or no logo.
- User-facing text and generated prose are Russian; developer contracts are English.
- AI is external and optional. No model or model credentials are bundled.

## Editor and Document Output

- The React/TypeScript SPA edits Markdown and title-page metadata with an A4 preview.
  Supported content includes headings, inline emphasis/code, lists, tables,
  fenced listings, images, and LaTeX formulas.
- The Python engine parses Markdown and generates DOCX with native OMML formulas
  or an explicitly selected simplified Unicode representation.
- Default body layout: A4, margins left/right/top/bottom 30/15/20/20 mm,
  Times New Roman 14 pt, 1.5 line spacing, justified text, 1.25 cm first-line indent.
  Title-page and caption styles have their own rules; the title-page number is hidden.
- Metadata supports multiple students and reviewers, optional work numbers,
  heading alignment, page numbering, caption visibility, and section page breaks.
- Image layouts are keyed by filename in `meta.image_layouts`; captions are not
  layout configuration. Author-supplied figure/table numbers are retained.
- Missing local images produce placeholders/warnings; web asks for confirmation
  before export. Preview pagination is approximate; inspect final DOCX/PDF.
- Subject presets store department, reviewers, agent instructions, and the last
  work number. Selecting a preset suggests the next number without incrementing
  the counter merely because the preset was selected again.

## Linter and Normcontrol

- The DOCX linter checks supported OpenXML formatting, headings/captions,
  paragraph geometry, structure, image/table references, and bibliography citations.
  Results expose errors, warnings, validity, score, and metrics.
- Web combines preview/structure feedback with normcontrol of generated or uploaded
  DOCX. Empty Markdown is neutral, not a successful report; references alone are not a body.
- Typography fixes are explicit operations, not silent rewriting of factual data.
  Browser spellcheck highlights possible mistakes without automatic correction.
- Bibliography records are `book`, `article`, `website`, or `standard` entries in
  `meta.references`. The final source section is generated in preview and DOCX;
  numbered citations such as `[1]` belong in body text. Python and TypeScript
  bibliography/typography mirrors must remain aligned.

## State, Revisions, and Live MCP

- Web stores text/metadata in localStorage and image originals/manifests in IndexedDB.
  Server sessions, image bytes, deletion markers, and bounded edit history remain in RAM.
  Full-project JSON export includes text, metadata, and images; browser storage is not a backup.
- Browser and live MCP writes require the fresh revision for the affected state.
  Stale HTTP writes return 409; the UI retains the local draft and requires explicit
  conflict resolution. Client IDs distinguish a tab's acknowledgements from remote edits.
- Browser SSE synchronizes session changes and reconciles image hashes after reconnect.
  A conflicting filename must not silently replace different image bytes.
- Live MCP uses `/api/mcp/sse?token=...`, including in standalone web. The browser's
  MCP modal supplies the session connection; tokens must not be shared publicly.
- Live tools read state/media, edit sections or revision-bound blocks, apply patches,
  update metadata/image layouts, inspect recent edits, roll back the last agent edit,
  lint, and fix typography. Writes must not silently overwrite adjacent sections.
- `assets/SKILL.md`, exposed as `report://rules/gost732` and through MCP prompts,
  is the compact canonical report-agent core. `write_report` embeds only this core;
  domain references are loaded on demand from `report://reference/figures`,
  `formulas`, `tables`, `style`, and `literals` (files in `assets/reference/`).
  Agents ask users about uncertain/missing facts outside report prose, never insert
  uncertainty placeholders or silently alter numbers, IP addresses, hashes, or identifiers.

### Additive MCP Safety Contract (1.1)

- Both transports expose `get_capabilities` without arguments: `transport`
  (`live` or `headless`), `contract_version`, runtime `pdf_export`/`pdf_converter`,
  `file_path: true`, `limits` (`image_bytes: 15728640`, `images_count: 150`,
  `markdown_bytes: 512000`), and `reference_resources` (the five reference URIs).
- `get_report_state` retains its default response and adds `verify_state` with
  `lint_after_last_change` and `export_allowed` booleans. Optional `detail: "digest"`
  returns only `sections` (`heading`, `word_count` for the section body including
  descendants), `image_refs` (`filename`, `status: attached|missing`, `location`),
  the three revisions, and `verify_state`; it omits Markdown and metadata.
  External image URLs retain legacy handling and are classified as attached.
- `lint_report` adds `unresolved_items` (`id`, `kind`, Russian `message`, `location`)
  and `export_blockers`, its critical subset. Stateless Markdown guards detect
  missing-data placeholders, internal prose paths, explicit preparation notes,
  and missing local image references, excluding fenced/inline code and link targets.
  Legitimate references such as "на рисунке 4.2" are not preparation notes.
  Kinds are `placeholder`, `internal_path`, `preparation_note`, `missing_image`;
  only placeholders and missing attachments block export. Legacy `is_valid`
  remains the absence of DOCX errors, not strict export readiness.
- `review_snapshot` is read-only: `markdown_content`, `metadata`, `images` manifest
  (filenames, sizes, SHA-256, `is_in_report`, no attachment base64), all revisions,
  `verify_state`, and freshly computed `lint`. It does not grant the export phase.
- Successful completion of `lint_report` on the current report is required after
  every actual text/metadata/image mutation, including browser updates and rollback.
  A lint with warnings still completes this phase; an exception or lint of other
  Markdown does not. No-op writes retain verification. `export_allowed` means
  current lint exists and its `export_blockers` is empty.
- `export_report` requires all three fresh `expected_*` revisions. Stale verification
  produces a Russian "сначала проверь отчёт" error. Nonempty blockers produce an
  error listing items; only literal boolean `confirm_blocked_export: true` bypasses
  these blockers, never the mandatory post-mutation lint. Confirmation is not sticky.
  Headless retains its existing filename/output-directory result. New live export
  accepts `format: docx|pdf` (default docx) and optional simple `filename`; it returns
  `filename`, `format`, `size_bytes`, `sha256`, and `base64_data` without server disk
  persistence. Browser `/api/generate` remains the existing independent HTTP contract.

## Headless MCP and Portable Profiles

- Headless is a separate stdio process with one RAM report, no browser or HTTP server.
  It exposes content/metadata/media editing, linting, profile import, and explicit export.
  Fresh text, metadata, and image revisions protect writes and exports.
- Headless export is restricted to a new simple filename in the pre-existing
  `--output-dir`; traversal, symlinks at the target, and overwrites are rejected.
- A portable profile is UTF-8 JSON with `format: "report-engine-profile"`,
  `version: 1`, `subject`, and `meta`, limited to 4 MiB at import boundaries.
  It carries one subject template and reusable title requisites, not report text,
  attached images, theme, bibliography, or image layouts.
- Web exports/imports profiles through the file menu; import adds/selects a preset
  and applies metadata through the existing conflict path without replacing the body/media.
- Live and headless `import_profile` accept exactly one of `profile` or `file_path`.
  File paths are local to the server and relative paths use its working directory.
  Live import requires `expected_meta_revision`; headless import creates a report
  if absent, otherwise requires that revision. Subject fields override corresponding meta fields.
- Web/live merge profile values into current metadata. Headless rebuilds metadata
  from the profile and defaults for report-only fields, retaining body/media.
  Headless accepts custom logos only through profile import as bounded base64 image
  data URLs, not filesystem paths. There is no headless profile-export tool.

## Delivery and PDF Capability

- Source web uses FastAPI and Vite; a built SPA can be served by the HTTP app.
  Docker consumes a prebuilt SPA and installs LibreOffice/fonts during image construction.
- Native PyInstaller onedir packages provide headless and web for Linux x64
  (Ubuntu 22.04 build runner) and Windows x64. They embed Python and dependencies;
  installed Python/Node.js and a source checkout are not runtime requirements.
- Standalone web binds to `127.0.0.1`, rejects foreign Host/Origin values, uses a
  fixed explicit port, serves the bundled SPA and live SSE MCP, and runs no Node process.
- Native packages do not include office converters or system document fonts.
  Required frozen data is checked byte-for-byte before assembly; web includes all SPA assets.
- DOCX is independent of PDF. `/api/capabilities` reports `pdf_export` and converter kind;
  headless tool discovery advertises PDF only when the local capability probe succeeds.
- Converter candidates are `soffice`/`libreoffice` or ONLYOFFICE Document Builder
  (`docbuilder`), with an optional `REPORT_ENGINE_PDF_CONVERTER` override.
  `REPORT_ENGINE_DISABLE_PDF` disables discovery. Conversion uses cleaned-up temporary files.
- A successful version probe is not proof of rendering fidelity. Target-machine
  conversion and fonts require separate verification; manual DOCX-to-PDF in an office
  editor is the fallback. No converter is downloaded at application runtime.

## Standalone Headless

### Scope and Runtime

Local agents create, edit, validate, and export one report through MCP stdio
without a browser or HTTP server. Entry point: `backend/app/headless.py`;
state and commands: `backend/app/engine/headless_report.py`.

Native PyInstaller onedir packages target Linux x64 (Ubuntu 22.04 build runner)
and Windows x64. Python and dependencies are embedded; no installed Python,
Node.js, frontend files, or source checkout is needed. Diagnostics and launcher
notices use stderr; stdout is reserved for MCP protocol data.

Source invocation: `python3 -m backend.app.headless --output-dir /absolute/output`.
Packaged invocation uses `report-engine-headless` (Windows: `.exe`) with the same
arguments. The output directory must already exist; the convenience launcher
creates its default `output` directory.

### Tool Contract

- Both MCP transports expose `batch` with 1–20 `{name, arguments}` calls executed
  sequentially. Results are ordered `{name, ok, result|error}` entries; errors
  continue by default, while `stop_on_error: true` stops at the first error.
  Nested batches and malformed call arrays fail preflight before any execution.
  All available tools are allowed; mutations are not rolled back, and revision
  arguments are never inferred from previous results. Live mutating batches hold
  one session MCP write lock across the complete sequence; read-only calls remain
  available without that lock.
- Image uploads accept exactly one of `base64_data` or `file_path` per image.
  Paths are server-local, expand `~`, and resolve relative to the process cwd;
  reads are bounded and run off the event loop in live MCP. The shared image
  limits are 15 MiB per file and 150 images per report, including HTTP generation.
  DOCX auditing retains its separate 25 MiB limit; error text follows each limit.
- Live `upload_images` retains atomic validation and `after_block_id` insertion
  with `expected_revision`. Headless `upload_images` checks one
  `expected_image_revision` before storing valid items, returning `uploaded_count`,
  ordered `results` (per-item `filename`, `ok`, `result|error`), and final revisions.
  Per-item `caption` and `insert_into_report` mirror single-image append behavior;
  any insertion additionally requires a fresh `expected_revision` before writes.

| Tools | Contract |
| --- | --- |
| `create_report` | Create one RAM draft; never silently reset an existing report. |
| `import_profile` | Accept `profile` object or local `file_path`, not both; validate `report-engine-profile` version 1 and size limits before applying. Create a draft if absent; otherwise require fresh `expected_meta_revision`. |
| `get_report_state` | Return Markdown, metadata, image manifest, `revision`, `meta_revision`, and `image_revision`. |
| `get_capabilities`, `review_snapshot` | Return runtime/limits/reference discovery or a read-only transferable review with lint; see the shared safety contract. |
| `list_images`, `get_image` | Read media/manifest; return native MCP image content for vision. |
| `upload_image`, `delete_image` | Require fresh image revision, reject duplicate names and invalid bytes; deletion rejects referenced images. Inserting an image into text also requires text revision. |
| `upload_images` | Upload 1–150 images with one image revision check and per-item results; valid items survive other items' errors. |
| `batch` | Execute 1–20 non-nested tool calls sequentially, including mutations and export, collecting results and optional stop-on-error. |
| `append_or_update_section` | Add or replace the body of an unambiguous heading using fresh text revision; retain adjacent sections. |
| `update_meta` | Apply supplied fields using fresh metadata revision. |
| `lint_report`, `autofix_typography` | Validate generated DOCX in RAM; typography writes require fresh text revision. |
| `export_report` | Explicitly write a new DOCX/PDF with all three fresh revisions into the configured output directory after current lint; critical blockers require `confirm_blocked_export: true`. |

- State and image bytes remain in RAM until process exit. No automatic draft persistence.
- Export accepts only a simple safe filename, rejects traversal/symlink targets
  and existing files, and returns path, size, and SHA-256.
- Profile import retains text/media but rebuilds metadata from profile values
  and defaults for report-only fields. Import before composing a report when possible.
  Subject values override corresponding title fields; the response includes `profile_subject`.
- `create_report`/`update_meta` reject custom logos. Profile import supports only
  base64 image data URLs (decoded logo at most 2 MiB), not filesystem paths;
  the existing 500 KiB metadata limit also applies.
- Resources include `report://rules/gost732`, `report://document/current`, and
  attached images plus all five `report://reference/*` resources; only core rules
  accompany the report-writing prompt. Native packages inventory and byte-verify
  each reference file independently of PyInstaller discovery.
- DOCX needs no office suite. `export_report` advertises PDF only when a local
  converter passes a version probe; PDF is not a separate tool or bundled runtime.

### Verification

- `tests/test_headless.py` covers the transport-free state core, revisions,
  profiles, media, safe exports, and independence from FastAPI imports.
  `tests/test_profiles.py` covers shared profile validation and local-file input.
  Real stdio initialize/discovery/create/edit/lint/export is a separate smoke check.
- `tests/test_packaging.py` rejects incomplete/corrupted frozen data, including
  DOCX templates and source directories; it checks launcher and package-guide contracts.
  These fixture tests are not native compiler/export tests.
- Native smoke: build on the target host, run from outside the checkout with PDF
  disabled, initialize MCP, create a report with native math/default logo, export,
  and inspect DOCX ZIP integrity, OMML, and media. Both Linux products have passed
  frozen DOCX export checks; Windows runtime remains unverified.
- Tagged CI currently builds and runs regressions per target, then invokes only
  frozen `--help`; full MCP/export smoke is separate. See [release status](RELEASE_STATUS.md).

## Standalone Local Web

### Scope and Runtime

Serve the existing React SPA and FastAPI API locally without installed Python,
Node.js, or a source checkout. Entry point: `backend/app/standalone_web.py`.
Native onedir packages embed Python/dependencies and all prebuilt SPA assets for
Linux x64 (Ubuntu 22.04 build runner) and Windows x64.

Source invocation with a prebuilt frontend:
`python3 -m backend.app.standalone_web --port 8000`.
Packaged entry point: `report-engine-web` (Windows: `.exe`);
convenience launchers: `start-web.sh` / `start-web.bat`.

### Contracts

- Bind only to `127.0.0.1`, default port 8000. Reject foreign HTTP Host/Origin
  values before delegating to the application; disable proxy-header trust here.
- Require the static build at startup. Never run npm/pip, download packages, or
  start a Node.js child process at runtime.
- Invalid or occupied ports fail clearly. Do not silently select a new origin:
  browser storage is origin-specific. An explicit `--port` change is allowed.
- Serve the full editor, preview, normcontrol, bibliography, project JSON, and
  profile import/export behavior described in the product spec.
- Also expose **live SSE MCP** at `/api/mcp/sse?token=...`; use the browser MCP
  modal for session configuration. This executable is not a stdio MCP server
  and does not depend on the headless process.
- Keep text/metadata in browser localStorage, images in IndexedDB, and server
  sessions in RAM. Retain revision checks, SSE acknowledgements, and explicit
  conflict resolution. Profiles transfer reusable requisites; projects back up reports.
- Print the loopback URL. Convenience launchers attempt browser opening after
  `/api/health` readiness; missing browser-opening tools do not prevent startup.
- Windows launchers use UTF-8 and pause on failure; Linux pauses only in an
  interactive terminal. Errors and end-user instructions are Russian.
- No native desktop shell or automatic update installation. Optional update
  notifications are failure-tolerant and do not download/install a release.
- Native packages omit office converters and system document fonts. Web's KaTeX
  fonts are static browser assets, not installed document fonts.
- `/api/capabilities` controls the optional PDF action. Missing converters leave
  DOCX active and the manual office-editor PDF fallback available. A successful
  converter probe is not proof of target-machine PDF fidelity.

### Verification

- `tests/test_standalone_web.py` covers loopback guards, the required static
  index, invalid/occupied ports, and disabled PDF. HTTP health/export and live
  MCP have separate API/session tests; real frozen startup/SPA checks are smoke,
  not unit coverage. Browser-service regressions protect shared editor behavior.
- `tests/test_packaging.py` verifies frozen DOCX resources and every SPA asset,
  rejects incomplete/corrupted packages, and covers package-guide content,
  failure recovery, URL selection, and readiness-gated opening.
- Native smoke from outside the checkout checks health, capabilities, SPA and
  assets, and HTTP DOCX generation with PDF disabled. Inspect the DOCX ZIP,
  native formulas, and default logo; both Linux products passed frozen export checks.
- Windows script checks on Linux are static. Actual Windows startup/export,
  target-machine PDF conversion, and antivirus behavior remain unverified.
  Tagged CI's frozen-executable check is currently `--help`, not full export smoke.
  See [release status](RELEASE_STATUS.md) and [build/release guide](release_tools/README.md).

## Verification and Documentation

Backend/API, MCP, profile, document, standalone, and packaging regressions live
in `tests/`; frontend service tests live beside their services. Frozen-data tests
use fixtures and do not replace native package export smoke tests.

See [release status](RELEASE_STATUS.md) and the
[maintainer build/release guide](release_tools/README.md).
