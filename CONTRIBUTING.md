# Contributing to Optrools

Thanks for contributing! This repo is primarily a documentation archive (OpenAPI navigation + version diff logs). Please keep changes focused, well-scoped, and easy to review.

## Quick start (GitHub Codespaces)

This repo includes a dev container (`.devcontainer/`) so you can contribute from GitHub Codespaces with minimal setup.

Common commands:

- `npm run lint` (Markdown lint)
- `npm run format` (Markdown format via Prettier)

## Local-only content (do not commit)

To reduce DMCA risk, OpenAPI spec JSON files are not stored in this repo. If you need spec files locally for development, place them under:

- `Local/OpenAPI Specs/`

Everything under `Local/` is ignored by git, except `.gitkeep` placeholder files that keep the folders present in the repo.

### Downloading the OpenAPI JSON

1. Download the OpenAPI JSON from the Optro Developer Portal.
2. Save it under `Local/OpenAPI Specs/` (for example: `Local/OpenAPI Specs/40.1.0.json`).

Notes:

- Do not commit vendor-provided specs or other proprietary artifacts.
- If you need to reference a spec version in docs, prefer linking to the official download location rather than checking files into the repo.

Reference (official download page):

- <https://developer.auditboard.com/reference/download-auditboard-openapi-specification>

## Making changes

### Documentation updates

- Keep Markdown changes minimal and consistent with existing style.
- If you edit diff logs, follow the naming conventions described in `OpenAPI/Specifications-DIFF/README.md`.

### Submitting a pull request

1. Create a fork and branch.
2. Run `npm run lint` before opening the PR.
3. Open a PR with a short summary and (if relevant) links to supporting references.
