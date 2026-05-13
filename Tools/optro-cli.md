# `optro` CLI

This repo includes a Python CLI named `optro` for working with the Optro (AuditBoard) API and the locally-downloaded OpenAPI specs.

## Setup

In GitHub Codespaces, the dev container installs the CLI automatically.

For local development:

1. `python -m pip install -e .`
2. Set configuration via environment variables:
   - `OPTRO_BASE_URL` (required)
   - `OPTRO_TOKEN` (recommended; API token used as a Bearer token)
   - `OPTRO_AUTH_HEADER` (defaults to `Authorization`)
   - `OPTRO_AUTH_SCHEME` (defaults to `Bearer`)

## Safety model

Commands that can write data default to dry-run. Use `--apply` to execute.

## Default authentication

By default, requests use:

- `Authorization: Bearer <OPTRO_TOKEN>`

## Commands

- `optro request ...` – raw HTTP wrapper (foundation).
- `optro bulk export|import ...` – bulk data movers (JSON / NDJSON).
- `optro access audit|analyze ...` – permission & access auditor.
- `optro evidence upload|attach ...` – evidence helper (upload + attach).
- `optro release digest ...` – release impact digest (uses `oasdiff`).
- `optro reports list|generate|pack ...` – report packager helpers.
- `optro sandbox run ...` – sandbox executor (plan files).
- `optro shadow export|diff|plan ...` – user/team allowlist “shadowing”.

Example inputs:

- `Tools/examples/report-pack-manifest.json`
- `Tools/examples/sandbox-plan.json`
