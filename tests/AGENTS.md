# Tests AGENTS.md

## Purpose

Own regression tests for the backend API, report generation, normocontrol, MCP sessions, and cross-layer behavior.

## Ownership

- `test_api.py` covers HTTP API behavior.
- `test_gost_normocontrol.py` covers generated-document formatting and validation.
- `test_mcp_sessions.py` covers session and MCP behavior.
- `test_headless.py`, `test_standalone_web.py`, and `test_packaging.py` cover standalone runtimes and native package assembly.
- The root and backend/frontend AGENTS.md files own implementation contracts.

## Local Contracts

- Tests must assert observable behavior rather than implementation details.
- Keep test code and test documentation in English; test fixtures and expected user-facing Russian text may remain Russian.
- Use fictional institutional/person names and reserved example domains in fixtures. Prefer initials followed by surname, except where alternative name order is the behavior under test.
- Do not weaken coverage by deleting assertions, skipping tests, or lowering thresholds to make an unrelated change pass.

## Work Guidance

- Add regression coverage for every bug fix or behavior change that can be tested deterministically.
- Keep fixtures isolated and avoid persistent test artifacts in the repository.
- Packaging regressions must reject missing or corrupted frozen runtime data, including DOCX templates and every web asset; unit fixtures must not require a prior frontend build.
- MCP regressions cover batch preflight/continuation/stop behavior, live write-lock serialization with concurrent reads, file-source exclusivity and size limits, and the distinct atomic live versus partial-success headless image-upload contracts.
- Launcher coverage checks Windows scripts statically and Linux scripts at runtime, including clean MCP stdout, failure exit codes, selected browser URLs, and readiness gating. Package guides must cover both MCP transports and novice recovery.

## Verification

- From the repository root, run `pytest -v`.
- Run the frontend test suite with `cd frontend && npm test` when browser-side behavior is affected.

## Child DOX Index

This directory has no nested AGENTS.md files.
