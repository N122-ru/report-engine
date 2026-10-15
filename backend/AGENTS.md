# Backend AGENTS.md

## Purpose

Own the FastAPI application that validates reports, generates DOCX/PDF files, serves the frontend, provides the live MCP session API, and supplies standalone runtimes.

## Ownership

- `app/` contains the backend application, domain models, document engine, session manager, and HTTP/MCP routes.
- `assets/` contains backend runtime assets used while serving or generating documents.
- `headless.py` and `standalone_web.py` define the standalone MCP and loopback web entry points.
- The repository root owns cross-cutting product rules and the top-level DOX index.

## Local Contracts

- Preserve the in-memory session model; do not introduce persistent report, image, or edit-history storage without an explicit product decision.
- Keep API schemas, revision checks, image handling, and generated-document behavior compatible with the root project guidance.
- User-facing API messages and generated report text remain Russian; implementation details, comments, tests, and developer documentation remain English.
- Keep the backend and frontend implementations aligned where the same formatter or validation behavior is mirrored.
- Validate the shared `report-engine-profile` format at the MCP boundary and apply it atomically under the current metadata revision.
- Treat PDF as a runtime capability; DOCX generation must not depend on an office converter.
- `app/engine/image_input.py` owns the shared 15 MiB image limit and 150-image count limit. HTTP, sessions, and headless re-export these constants; local MCP image paths use bounded reads and exactly one of `base64_data` or `file_path`.
- `batch` preflights all 1–20 calls and rejects nesting before execution. Calls run sequentially without rollback; live batches containing mutations hold `session.mcp_write_lock` for the entire sequence, while read-only calls remain unlocked.
- Live `upload_images` remains atomic; headless `upload_images` checks revisions once and returns ordered per-item errors while retaining valid uploads. Live file reads run through `asyncio.to_thread`, with revision rechecks before writes.
- `report_safety.py` owns stateless prose guards, digest data, and verification state shared by both MCP transports. Every actual text/metadata/image mutation invalidates lint, including browser writes and rollback; no-op writes do not.
- MCP export requires a completed lint of the current report. Only literal `confirm_blocked_export: true` bypasses critical placeholders/missing-image blockers, never the lint phase. `review_snapshot` and alternate-text lint do not advance the phase.
- Live `export_report` returns document bytes as base64 without server persistence; headless retains exclusive file creation in its configured output directory. The independent browser HTTP generation contract is unchanged.
- `agent_resources.py` serves the canonical core and five allowlisted references in source/frozen runtimes. `get_capabilities` describes these resources, their UTF-8 hash/size versions, and runtime limits; `write_report` embeds only the core. Both MCP transports expose `agent_onboarding` and short Russian onboarding instructions in `initialize`; the local skill is client cache only and is never stored by the server.
- Onboarding has no questionnaire: at most one short question clarifies one-shot versus ongoing use. One-shot skips the playbook; ongoing or unknown use proceeds autonomously. The agent maintains client optimizations after every session without changing the server manifest; preserve the environment checklist and manifest header.
- Live and headless MCP share the `snapshot_id` contract, structured revision conflicts, operation-id replay protection, and batch result references; legacy revision arguments remain supported.
- `app/engine/local_files.py` owns the server-local file-source policy: headless always reads paths, the portable web launcher enables them at startup, and networked deployments stay base64-only. Live `file_path` handling rejects other runs with an actionable error, omits the argument from `tools/list` schemas there, and still validates image signatures before storing. Operation replay caches are bounded to 8 MiB with a 256 KiB per-result limit.

## Work Guidance

- Prefer small, isolated changes in `app/engine` and preserve existing low-level DOCX/XML conventions.
- Update regression tests when changing report structure, validation, session behavior, or public API contracts.
- Avoid writing temporary or diagnostic data to permanent project storage.

## Verification

- From the repository root, run `pytest -v`.
- For document-generation changes, verify the generated DOCX/PDF behavior when the required local tools are available.
- Run headless and standalone runtime tests when changing their entry points or packaging contracts.

## Child DOX Index

- `app/` — backend application code, owned by this document; no nested AGENTS.md is currently required.
- `assets/` — backend runtime assets, owned by this document; no nested AGENTS.md is currently required.
