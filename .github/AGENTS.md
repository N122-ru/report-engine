# GitHub Workflows AGENTS.md

## Purpose

Own quality and native release workflows for the integrated repository.

## Ownership

- `workflows/ci.yml` runs repository quality gates.
- `workflows/standalone-packages.yml` builds and publishes versioned packages for both products and supported native runners.
- `workflows/docker.yml` builds, smoke-tests, archives, and attaches the versioned Docker image for tagged releases.
- Root `requirements-dev.txt` declares the shared Python test dependencies installed by both workflows.

## Local Contracts

- Release artifacts are versioned `headless` and `web` packages for Ubuntu 22.04 and Windows x64.
- Workflows must not store credentials, office suites, or fonts in the repository.
- PDF is a runtime capability, not a bundled release feature; release notes must state the manual DOCX fallback.
- The Docker workflow does not publish to a container registry; its tarball is uploaded as a workflow artifact and attached only for matching tag-triggered releases.
- Both workflows install root `requirements-dev.txt` before pytest. Test tooling must stay separate from runtime and PyInstaller requirements.
- Every release job installs both product requirement files: the full regression suite needs the HTTP test client, and the packaging resource inventory needs the pinned JSON Schema dependencies from the headless set even for web.

## Work Guidance

### Maintainer Release Procedure

- Follow the version-bump, verification, and native smoke procedure in [`release_tools/README.md`](../release_tools/README.md#maintainer-release-procedure). `VERSION` is canonical; release notes are Russian-only, user-facing, and kept on GitHub rather than in a repository file.
- A maintainer explicitly publishes a matching `vX.Y.Z` tag. Do not tag or push as an incidental part of documentation work.
- `standalone-packages.yml` runs four native builds: headless/web on Ubuntu 22.04 and Windows Server 2022 x64. Each job builds the frontend, runs pytest, rejects a tag/`VERSION` mismatch, assembles the package, checks the executable with `--help`, and uploads a versioned ZIP artifact.
- The publish job waits for all builds, downloads their artifacts, and attaches the four ZIPs to GitHub Release without setting or generating its body. The maintainer supplies Russian-only user-facing notes; for `v0.1.0`, notes introduce the first release instead of using a changelog-style list. Confirm the published assets and disclose the runtime/PDF/antivirus verification limits recorded in `RELEASE_STATUS.md`.
- CI's `--help` smoke is not packaged DOCX export or target-machine acceptance; preserve the separate full smoke procedure in the build guide.

## Verification

- Keep workflow commands and maintainer instructions aligned with `release_tools/README.md`; the root README is an end-user manual, not a release runbook.

## Child DOX Index

No nested documents.
