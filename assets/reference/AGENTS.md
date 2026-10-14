# Report References AGENTS.md

## Purpose

Own detailed domain guidance loaded on demand by report agents.

## Ownership

- `figures.md`, `formulas.md`, `tables.md`, `style.md`, and `literals.md` are served by both MCP transports as `report://reference/<name>`.
- Parent `assets/AGENTS.md` owns the compact workflow core and shared runtime assets.

## Local Contracts

- Preserve Russian domain guidance and user-facing examples; developer contracts remain English.
- Keep reference names allowlisted in `agent_resources.py` and required by `release_tools/build_release.py`.
- References are not embedded in `write_report`; the core points to them by topic.

## Work Guidance

- Preserve factual literals and legitimate report figure references; preparation notes and uncertainty placeholders do not belong in report prose.

## Verification

- Run `python3 -m pytest tests/test_mcp_safety.py tests/test_packaging.py -v`.

## Child DOX Index

No nested documents.
