#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _spec_path_for_version(specs_dir: Path, version: str) -> Path:
    if version == "40.0.0":
        alias = specs_dir / "40.0.0-dev (39.3.0).json"
        if alias.exists():
            return alias
        raise FileNotFoundError(
            f"Spec for version {version!r} is expected at {alias} (alias mapping)."
        )

    exact = specs_dir / f"{version}.json"
    if exact.exists():
        return exact

    matches = sorted(specs_dir.glob(f"{version}*.json"))
    if len(matches) == 1:
        return matches[0]

    if not matches:
        raise FileNotFoundError(
            f"No local spec file found for version {version!r}. "
            f"Expected {exact} or any {version}*.json under {specs_dir}."
        )

    raise FileNotFoundError(
        f"Multiple candidate spec files found for version {version!r}: "
        + ", ".join(p.name for p in matches)
        + f". Create {exact.name} to disambiguate."
    )


def _run_oasdiff(oasdiff_bin: str, base: Path, revision: Path) -> str:
    cmd = [oasdiff_bin, "changelog", "-f", "markdown", str(base), str(revision)]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "oasdiff failed:\n"
            + "Command: "
            + " ".join(cmd)
            + "\n\nSTDOUT:\n"
            + proc.stdout
            + "\n\nSTDERR:\n"
            + proc.stderr
        )
    return proc.stdout


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate OpenAPI diff logs under OpenAPI/Specifications-DIFF using local specs in Local/OpenAPI Specs."
    )
    parser.add_argument(
        "--diff-root",
        default="OpenAPI/Specifications-DIFF",
        help="Root directory containing FROM-*/<from>-<to>.md diff files.",
    )
    parser.add_argument(
        "--specs-dir",
        default="Local/OpenAPI Specs",
        help="Directory containing local OpenAPI JSON specs (ignored by git).",
    )
    parser.add_argument(
        "--oasdiff",
        default=os.environ.get("OASDIFF_BIN", "oasdiff"),
        help="Path to the oasdiff binary (or set OASDIFF_BIN).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute diffs but do not write any files.",
    )
    args = parser.parse_args(argv)

    diff_root = Path(args.diff_root)
    specs_dir = Path(args.specs_dir)
    if not diff_root.exists():
        print(f"diff root not found: {diff_root}", file=sys.stderr)
        return 2
    if not specs_dir.exists():
        print(f"specs dir not found: {specs_dir}", file=sys.stderr)
        return 2

    diff_files = sorted(diff_root.glob("FROM-*/*.md"))
    if not diff_files:
        print(f"no diff files found under {diff_root}/FROM-*", file=sys.stderr)
        return 2

    updated = 0
    for path in diff_files:
        from_dir_version = path.parent.name.removeprefix("FROM-")
        stem = path.stem
        if "-" not in stem:
            continue
        from_version, to_version = stem.split("-", 1)
        if from_version != from_dir_version:
            raise RuntimeError(
                f"Diff file name does not match folder: {path} (folder says {from_dir_version}, file says {from_version})"
            )

        base_spec = _spec_path_for_version(specs_dir, from_version)
        revision_spec = _spec_path_for_version(specs_dir, to_version)

        out = _run_oasdiff(args.oasdiff, base_spec, revision_spec)
        if not out.strip():
            raise RuntimeError(f"oasdiff produced empty output for {from_version} -> {to_version}")

        if not args.dry_run:
            path.write_text(out, encoding="utf-8", newline="\n")
        updated += 1
        print(f"updated {path}")

    print(f"done: regenerated {updated} diff files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
