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
