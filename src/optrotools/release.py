from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .specs import resolve_spec_path


@dataclass(frozen=True)
class ReleaseDigest:
    from_version: str
    to_version: str
    summary: dict[str, Any]
    breaking: dict[str, Any] | None


def _run_oasdiff_json(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(args, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"oasdiff failed: {' '.join(args)}\n\nSTDERR:\n{proc.stderr}\n\nSTDOUT:\n{proc.stdout}")
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def generate_release_digest(*, from_version: str, to_version: str, specs_dir: Path) -> ReleaseDigest:
    oasdiff = os.environ.get("OASDIFF_BIN", "oasdiff")
    base = resolve_spec_path(specs_dir, from_version)
    rev = resolve_spec_path(specs_dir, to_version)

    summary = _run_oasdiff_json([oasdiff, "summary", "-f", "json", str(base), str(rev)])
    breaking = _run_oasdiff_json([oasdiff, "breaking", "-f", "json", str(base), str(rev)])
    return ReleaseDigest(from_version=from_version, to_version=to_version, summary=summary, breaking=breaking)


def render_release_digest_md(d: ReleaseDigest) -> str:
    lines: list[str] = []
    lines.append(f"# Release impact digest: {d.from_version} → {d.to_version}")
    lines.append("")

    # Summary structure varies by oasdiff version; render conservatively.
    if d.summary:
        lines.append("## Summary (oasdiff)")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(d.summary, indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")

    if d.breaking:
        lines.append("## Breaking changes (oasdiff)")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(d.breaking, indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)

