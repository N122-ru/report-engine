# Shared Assets AGENTS.md

## Purpose

Own shared runtime assets that are consumed by the backend, frontend, or report agent.

## Ownership

- `SKILL.md` is the canonical instruction source for the live report agent.
- Image and other binary assets are project resources, not source-code modules.
- The repository root owns product-wide behavior and language rules.

## Local Contracts

- Keep `SKILL.md` aligned with the live MCP tools and the report-generation behavior.
- Document profile import (`import_profile`, format discriminator, version, and revision precondition) in `SKILL.md` whenever that tool contract changes.
- Keep batch ordering/error behavior, server-local image paths, image limits, and live/headless upload revision and partial-success differences visible in `SKILL.md`.
- Do not add credentials, personal data, generated reports, or temporary files to this directory.
- Internal instructions and metadata are written in English; text intended for report users remains Russian.

## Work Guidance

- Update the canonical instruction source when an MCP workflow or report contract changes.
- Keep binary assets small, intentional, and referenced by the code that serves or packages them.

## Verification

- Run the repository test suite after changing `SKILL.md` or runtime assets.
- Verify that changed assets are included in the intended Docker/runtime path.

## Child DOX Index

This directory has no nested AGENTS.md files.
