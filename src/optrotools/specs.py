from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SpecRef:
    version: str
    path: Path


def resolve_spec_path(specs_dir: Path, version: str) -> Path:
    # Repo convention: use the portal's 40.0.0-dev (39.3.0) file when a diff asks for 40.0.0.
    if version == "40.0.0":
        alias = specs_dir / "40.0.0-dev (39.3.0).json"
        if alias.exists():
            return alias
        raise FileNotFoundError(f"Missing 40.0.0 alias spec at {alias}")

    exact = specs_dir / f"{version}.json"
    if exact.exists():
        return exact

    matches = sorted(specs_dir.glob(f"{version}*.json"))
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(f"No spec found for {version!r} under {specs_dir}")
    raise FileNotFoundError(
        f"Multiple spec candidates for {version!r}: {', '.join(p.name for p in matches)}. Create {exact.name}."
    )


def list_unique_versions(specs_dir: Path) -> list[str]:
    versions: dict[str, list[Path]] = {}
    for p in specs_dir.glob("*.json"):
        obj = json.loads(p.read_text("utf-8"))
        v = (obj.get("info") or {}).get("version")
        if not v:
            continue
        versions.setdefault(str(v), []).append(p)

    # Treat portal 40.0.0-dev as 40.0.0 for adjacent chain generation.
    ordered = sorted(set(versions.keys()), key=_semantic_key)
    if "40.0.0-dev" in ordered:
        ordered = [v for v in ordered if v != "40.0.0-dev"]
        ordered.append("40.0.0")
        ordered = sorted(set(ordered), key=_semantic_key)
    return ordered


def _semantic_key(version: str) -> tuple[list[int], bool, str]:
    nums = [int(x) for x in re.findall(r"\d+", version)]
    is_dev = "dev" in version
    return (nums, is_dev, version)


def spec_list_key_from_path(path: str) -> str:
    # For list endpoints like /users -> users
    return path.strip("/").split("/", 1)[0]

