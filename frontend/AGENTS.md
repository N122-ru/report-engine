# Frontend AGENTS.md

## Purpose

Own the React and TypeScript single-page application, its browser-side services, report editor, preview, and static frontend assets.

## Ownership

- `src/` contains the application entry point, components, services, and shared types.
- `public/` contains static files copied into the frontend build.
- The repository root owns cross-cutting product rules and the top-level DOX index.

## Local Contracts

- Keep user-facing UI copy, validation messages, and report-facing text in Russian.
- Keep TypeScript, CSS class names, tests, comments, and developer documentation in English.
- Preserve parity between browser-side mirrors and their backend counterparts where the root guidance requires it.
- Custom logos are limited to 2 MiB and accepted only when their bytes match PNG or JPEG signatures; client checks are UX validation and the backend remains authoritative.
- `src/services/imageRefs.ts` owns browser-side Markdown image-name decoding and matching. Keep it behaviorally aligned with `backend/app/engine/image_refs.py`; ambiguous normalized names must remain unresolved.
- Keep editor state, browser storage, image synchronization, revision handling, and conflict resolution behavior explicit and lossless.
- Keep `report-engine-profile` JSON serialization versioned and validate profile imports before adding templates or changing requisites.
- Profile imports must retain the existing session `meta_revision` conflict path and must not silently overwrite remote metadata.
- Treat PDF availability as a server-reported optional capability and keep DOCX export available when it is absent.
- A4 preview pagination is owned by `src/services/previewPagination.ts`: estimate wrapped table cells at equal fixed column widths, include headers/captions/padding, and reserve 10 px below the 700 px body budget. Split prose by estimated 21 px lines while retaining inline formatting; indent only the original paragraph start. Preserve heading keep-with-next and explicit page breaks. Preview pagination remains approximate; DOCX/PDF determines final layout.

## Work Guidance

- Follow the existing React, TypeScript, Tailwind, and Vite patterns.
- Prefer accessible native controls and preserve responsive behavior on desktop and mobile layouts.
- Add or update focused service tests when changing parsing, storage, insertion, synchronization, or formatting behavior.

## Verification

- Run `npm test` from `frontend/` for browser-service tests.
- Run `npm run build` from `frontend/` for TypeScript and Vite verification.
- Run `npm run lint` from `frontend/` when changing frontend source code.

## Child DOX Index

- `src/` — application code, owned by this document; no nested AGENTS.md is currently required.
- `public/` — static frontend assets, owned by this document; no nested AGENTS.md is currently required.
