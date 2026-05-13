from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.pretty import Pretty

from .config import load_config
from .http import OptroClient
from .release import generate_release_digest, render_release_digest_md
from .specs import resolve_spec_path

app = typer.Typer(help="Optro tools: API helpers, bulk movers, audits, evidence helpers, and spec-based utilities.")
console = Console()


def _client(
    *,
    base_url: str | None,
    token: str | None,
    auth_header: str | None,
    auth_scheme: str | None,
    timeout_s: float | None,
    insecure: bool,
    dry_run: bool,
) -> OptroClient:
    cfg = load_config(
        base_url=base_url,
        token=token,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        timeout_s=timeout_s,
        verify_tls=not insecure,
    )
    return OptroClient(cfg, dry_run=dry_run)


def _extract_items(payload: Any, *, key: str | None) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if key and key in payload and isinstance(payload[key], list):
            return payload[key]
        # heuristic fallbacks
        for candidate in ("items", "data", "results"):
            if candidate in payload and isinstance(payload[candidate], list):
                return payload[candidate]
    raise ValueError("Unsupported response shape; provide `--key` to select the list field.")


@app.command("request")
def raw_request(
    method: str = typer.Argument(..., help="HTTP method, e.g. GET/POST/PUT/DELETE"),
    path_or_url: str = typer.Argument(..., help="Path like /tests or full URL"),
    params: list[str] = typer.Option(None, "--param", help="Query param key=value (repeatable)"),
    data: str | None = typer.Option(None, "--json", help="JSON body as a string"),
    base_url: str | None = typer.Option(None, "--base-url", envvar="OPTRO_BASE_URL"),
    token: str | None = typer.Option(None, "--token", envvar="OPTRO_TOKEN"),
    auth_header: str | None = typer.Option(None, "--auth-header", envvar="OPTRO_AUTH_HEADER"),
    auth_scheme: str | None = typer.Option("Bearer", "--auth-scheme", envvar="OPTRO_AUTH_SCHEME"),
    timeout_s: float | None = typer.Option(None, "--timeout"),
    insecure: bool = typer.Option(False, "--insecure", help="Disable TLS verification"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be done, without making requests"),
) -> None:
    """Low-level request helper (foundation for all other commands)."""
    p: dict[str, str] = {}
    for item in params or []:
        if "=" not in item:
            raise typer.BadParameter("--param must be key=value")
        k, v = item.split("=", 1)
        p[k] = v
    body = json.loads(data) if data else None
    client = _client(
        base_url=base_url,
        token=token,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        timeout_s=timeout_s,
        insecure=insecure,
        dry_run=dry_run,
    )
    out = client.request_json(method, path_or_url, params=p or None, json_body=body)
    console.print(Pretty(out))


bulk_app = typer.Typer(help="Bulk export/import for common resources.")
app.add_typer(bulk_app, name="bulk")


@bulk_app.command("export")
def bulk_export(
    resource: str = typer.Argument(..., help="Resource path, e.g. tests, issues, users"),
    out: Path = typer.Option(..., "--out", help="Output file (.json or .ndjson)"),
    key: str | None = typer.Option(None, "--key", help="Response key holding the list (e.g. users, issues)"),
    base_url: str | None = typer.Option(None, "--base-url", envvar="OPTRO_BASE_URL"),
    token: str | None = typer.Option(None, "--token", envvar="OPTRO_TOKEN"),
    auth_header: str | None = typer.Option(None, "--auth-header", envvar="OPTRO_AUTH_HEADER"),
    auth_scheme: str | None = typer.Option("Bearer", "--auth-scheme", envvar="OPTRO_AUTH_SCHEME"),
    timeout_s: float | None = typer.Option(None, "--timeout"),
    insecure: bool = typer.Option(False, "--insecure"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Export a collection endpoint to JSON/NDJSON. Pagination is best-effort (API-dependent)."""
    client = _client(
        base_url=base_url,
        token=token,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        timeout_s=timeout_s,
        insecure=insecure,
        dry_run=dry_run,
    )
    path = resource if resource.startswith("/") else f"/{resource}"
    payload = client.request_json("GET", path)
    items = _extract_items(payload, key=key)

    if out.suffix.lower() == ".ndjson":
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="\n") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False))
                f.write("\n")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    console.print(f"Wrote {len(items)} items to {out}")


@bulk_app.command("import")
def bulk_import(
    resource: str = typer.Argument(..., help="Resource path, e.g. tests, issues"),
    inp: Path = typer.Option(..., "--in", help="Input file (.json array or .ndjson)"),
    wrap_key: str | None = typer.Option(None, "--wrap-key", help="Wrap each item as {wrap_key: item} for POST"),
    apply: bool = typer.Option(False, "--apply", help="Actually POST items (default is dry-run)"),
    base_url: str | None = typer.Option(None, "--base-url", envvar="OPTRO_BASE_URL"),
    token: str | None = typer.Option(None, "--token", envvar="OPTRO_TOKEN"),
    auth_header: str | None = typer.Option(None, "--auth-header", envvar="OPTRO_AUTH_HEADER"),
    auth_scheme: str | None = typer.Option("Bearer", "--auth-scheme", envvar="OPTRO_AUTH_SCHEME"),
    timeout_s: float | None = typer.Option(None, "--timeout"),
    insecure: bool = typer.Option(False, "--insecure"),
) -> None:
    """Import items by POSTing to a collection endpoint. Defaults to dry-run; use --apply to execute."""
    client = _client(
        base_url=base_url,
        token=token,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        timeout_s=timeout_s,
        insecure=insecure,
        dry_run=not apply,
    )
    text = inp.read_text("utf-8")
    items: list[Any]
    if inp.suffix.lower() == ".ndjson":
        items = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise typer.BadParameter("JSON input must be an array; use .ndjson for line-delimited JSON.")
        items = parsed

    path = resource if resource.startswith("/") else f"/{resource}"
    for idx, item in enumerate(items, start=1):
        body = {wrap_key: item} if wrap_key else item
        out = client.request_json("POST", path, json_body=body)
        if client.dry_run:
            console.print(f"[dry-run] would import item {idx}/{len(items)}")
        else:
            console.print(f"imported item {idx}/{len(items)}")
            console.print(Pretty(out))


access_app = typer.Typer(help="Permission & access auditor (users/roles/allowed users/teams).")
app.add_typer(access_app, name="access")


@access_app.command("audit")
def access_audit(
    out: Path = typer.Option(..., "--out", help="Write audit report JSON here"),
    base_url: str | None = typer.Option(None, "--base-url", envvar="OPTRO_BASE_URL"),
    token: str | None = typer.Option(None, "--token", envvar="OPTRO_TOKEN"),
    auth_header: str | None = typer.Option(None, "--auth-header", envvar="OPTRO_AUTH_HEADER"),
    auth_scheme: str | None = typer.Option("Bearer", "--auth-scheme", envvar="OPTRO_AUTH_SCHEME"),
    timeout_s: float | None = typer.Option(None, "--timeout"),
    insecure: bool = typer.Option(False, "--insecure"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Fetch access-related resources and write a JSON audit snapshot."""
    client = _client(
        base_url=base_url,
        token=token,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        timeout_s=timeout_s,
        insecure=insecure,
        dry_run=dry_run,
    )
    snapshot = {
        "base_url": base_url or os.getenv("OPTRO_BASE_URL"),
        "users": client.request_json("GET", "/users"),
        "roles": client.request_json("GET", "/roles"),
        "allowed_users": client.request_json("GET", "/allowed_users"),
        "allowed_teams": client.request_json("GET", "/allowed_teams"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    console.print(f"Wrote audit snapshot to {out}")


evidence_app = typer.Typer(help="Evidence helper: upload files and attach to entities.")
app.add_typer(evidence_app, name="evidence")


@evidence_app.command("upload")
def evidence_upload(
    file_path: Path = typer.Argument(..., exists=True),
    fileable_type: str = typer.Option(..., "--fileable-type", help="Entity type, e.g. Test, Issue, TaskItem"),
    fileable_id: int = typer.Option(..., "--fileable-id", help="Entity ID"),
    meta: str | None = typer.Option(None, "--meta"),
    apply: bool = typer.Option(False, "--apply", help="Actually upload (default is dry-run)"),
    base_url: str | None = typer.Option(None, "--base-url", envvar="OPTRO_BASE_URL"),
    token: str | None = typer.Option(None, "--token", envvar="OPTRO_TOKEN"),
    auth_header: str | None = typer.Option(None, "--auth-header", envvar="OPTRO_AUTH_HEADER"),
    auth_scheme: str | None = typer.Option("Bearer", "--auth-scheme", envvar="OPTRO_AUTH_SCHEME"),
    timeout_s: float | None = typer.Option(None, "--timeout"),
    insecure: bool = typer.Option(False, "--insecure"),
) -> None:
    """
    Upload a local file as evidence using `/files/upload`.

    The OpenAPI schema for the `file` field is untyped; this command sends base64 by default.
    If your tenant expects a different representation, use `optro request` to craft the call.
    """
    client = _client(
        base_url=base_url,
        token=token,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        timeout_s=timeout_s,
        insecure=insecure,
        dry_run=not apply,
    )
    b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
    payload: dict[str, Any] = {
        "fileable_type": fileable_type,
        "fileable_id": fileable_id,
        "file": b64,
    }
    if meta is not None:
        payload["meta"] = meta
    out = client.request_json("POST", "/files/upload", json_body=payload)
    console.print(Pretty(out))


@evidence_app.command("attach")
def evidence_attach(
    file_id: int = typer.Option(..., "--file-id", help="File ID (from /files/upload or /files)"),
    attachable_type: str = typer.Option(..., "--attachable-type", help="Entity type, e.g. Test, Issue, TaskItem"),
    attachable_id: int = typer.Option(..., "--attachable-id", help="Entity ID"),
    name: str = typer.Option(..., "--name", help="Attachment name"),
    apply: bool = typer.Option(False, "--apply"),
    base_url: str | None = typer.Option(None, "--base-url", envvar="OPTRO_BASE_URL"),
    token: str | None = typer.Option(None, "--token", envvar="OPTRO_TOKEN"),
    auth_header: str | None = typer.Option(None, "--auth-header", envvar="OPTRO_AUTH_HEADER"),
    auth_scheme: str | None = typer.Option("Bearer", "--auth-scheme", envvar="OPTRO_AUTH_SCHEME"),
    timeout_s: float | None = typer.Option(None, "--timeout"),
    insecure: bool = typer.Option(False, "--insecure"),
) -> None:
    """Create an attachment linking a file to an entity via `/attachments`."""
    client = _client(
        base_url=base_url,
        token=token,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        timeout_s=timeout_s,
        insecure=insecure,
        dry_run=not apply,
    )
    body = {"attachment": {"file_id": file_id, "attachable_type": attachable_type, "attachable_id": attachable_id, "name": name}}
    out = client.request_json("POST", "/attachments", json_body=body)
    console.print(Pretty(out))


release_app = typer.Typer(help="Release impact digest from OpenAPI specs (uses oasdiff).")
app.add_typer(release_app, name="release")


@release_app.command("digest")
def release_digest(
    from_version: str = typer.Option(..., "--from"),
    to_version: str = typer.Option(..., "--to"),
    specs_dir: Path = typer.Option(Path("Local/OpenAPI Specs"), "--specs-dir"),
    out: Path | None = typer.Option(None, "--out", help="Write markdown digest to this file"),
) -> None:
    d = generate_release_digest(from_version=from_version, to_version=to_version, specs_dir=specs_dir)
    md = render_release_digest_md(d)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8", newline="\n")
        console.print(f"Wrote digest to {out}")
    else:
        console.print(md)


reports_app = typer.Typer(help="Report generation and packaging helpers.")
app.add_typer(reports_app, name="reports")


@reports_app.command("list")
def reports_list(
    base_url: str | None = typer.Option(None, "--base-url", envvar="OPTRO_BASE_URL"),
    token: str | None = typer.Option(None, "--token", envvar="OPTRO_TOKEN"),
    auth_header: str | None = typer.Option(None, "--auth-header", envvar="OPTRO_AUTH_HEADER"),
    auth_scheme: str | None = typer.Option("Bearer", "--auth-scheme", envvar="OPTRO_AUTH_SCHEME"),
    timeout_s: float | None = typer.Option(None, "--timeout"),
    insecure: bool = typer.Option(False, "--insecure"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    client = _client(
        base_url=base_url,
        token=token,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        timeout_s=timeout_s,
        insecure=insecure,
        dry_run=dry_run,
    )
    out = client.request_json("GET", "/reports")
    console.print(Pretty(out))


@reports_app.command("generate")
def reports_generate(
    endpoint: str = typer.Option("generate", "--endpoint", help="One of: generate, generate/auditable_entity, ..."),
    payload_json: Path = typer.Option(..., "--payload", exists=True, help="JSON file to POST as request body"),
    apply: bool = typer.Option(False, "--apply", help="Actually call the API (default dry-run)"),
    base_url: str | None = typer.Option(None, "--base-url", envvar="OPTRO_BASE_URL"),
    token: str | None = typer.Option(None, "--token", envvar="OPTRO_TOKEN"),
    auth_header: str | None = typer.Option(None, "--auth-header", envvar="OPTRO_AUTH_HEADER"),
    auth_scheme: str | None = typer.Option("Bearer", "--auth-scheme", envvar="OPTRO_AUTH_SCHEME"),
    timeout_s: float | None = typer.Option(None, "--timeout"),
    insecure: bool = typer.Option(False, "--insecure"),
) -> None:
    client = _client(
        base_url=base_url,
        token=token,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        timeout_s=timeout_s,
        insecure=insecure,
        dry_run=not apply,
    )
    body = json.loads(payload_json.read_text("utf-8"))
    path = endpoint.strip("/")
    out = client.request_json("POST", f"/reports/{path}", json_body=body)
    console.print(Pretty(out))


@reports_app.command("pack")
def reports_pack(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        exists=True,
        help="JSON array of jobs: {name, endpoint, payload} or {name, endpoint, payload_path}.",
    ),
    out_dir: Path = typer.Option(Path("Local/report-pack"), "--out-dir", help="Directory to write outputs into"),
    zip_path: Path | None = typer.Option(None, "--zip", help="Optional .zip file to create from out-dir"),
    apply: bool = typer.Option(False, "--apply", help="Actually call the API (default dry-run)"),
    base_url: str | None = typer.Option(None, "--base-url", envvar="OPTRO_BASE_URL"),
    token: str | None = typer.Option(None, "--token", envvar="OPTRO_TOKEN"),
    auth_header: str | None = typer.Option(None, "--auth-header", envvar="OPTRO_AUTH_HEADER"),
    auth_scheme: str | None = typer.Option("Bearer", "--auth-scheme", envvar="OPTRO_AUTH_SCHEME"),
    timeout_s: float | None = typer.Option(None, "--timeout"),
    insecure: bool = typer.Option(False, "--insecure"),
) -> None:
    """
    Generate a set of reports described by a manifest and save outputs locally.

    If a response includes a URL-like field (url, download_url, file_url), this command will attempt to download it.
    """
    import zipfile

    client = _client(
        base_url=base_url,
        token=token,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        timeout_s=timeout_s,
        insecure=insecure,
        dry_run=not apply,
    )
    jobs = json.loads(manifest.read_text("utf-8"))
    if not isinstance(jobs, list):
        raise typer.BadParameter("Manifest must be a JSON array.")

    out_dir.mkdir(parents=True, exist_ok=True)

    def find_url(obj: Any) -> str | None:
        if isinstance(obj, dict):
            for k in ("download_url", "file_url", "url"):
                v = obj.get(k)
                if isinstance(v, str) and v.startswith("http"):
                    return v
            # common nested shapes
            for k in ("report", "file", "data"):
                u = find_url(obj.get(k))
                if u:
                    return u
        return None

    for idx, job in enumerate(jobs, start=1):
        name = (job.get("name") or f"job-{idx}").strip()
        endpoint = (job.get("endpoint") or "generate").strip("/ ")
        payload: Any
        if "payload_path" in job:
            payload = json.loads(Path(job["payload_path"]).read_text("utf-8"))
        else:
            payload = job.get("payload")
        if payload is None:
            raise typer.BadParameter(f"Job {name} missing payload/payload_path")

        resp = client.request_json("POST", f"/reports/{endpoint}", json_body=payload)
        (out_dir / f"{name}.response.json").write_text(
            json.dumps(resp, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        url = find_url(resp)
        if url:
            target = out_dir / f"{name}.bin"
            if client.dry_run:
                console.print(f"[dry-run] would download {url} -> {target}")
            else:
                client.download_to_path(url, str(target))
                console.print(f"downloaded {url} -> {target}")

    if zip_path:
        if client.dry_run:
            console.print(f"[dry-run] would create zip at {zip_path} from {out_dir}")
        else:
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for p in sorted(out_dir.rglob("*")):
                    if p.is_file():
                        z.write(p, arcname=str(p.relative_to(out_dir)))
            console.print(f"wrote {zip_path}")


sandbox_app = typer.Typer(help="Sandbox executor: safe-by-default execution via --apply.")
app.add_typer(sandbox_app, name="sandbox")


@sandbox_app.command("run")
def sandbox_run(
    plan: Path = typer.Option(..., "--plan", exists=True, help="JSON plan: list of {method,path,params,json}"),
    apply: bool = typer.Option(False, "--apply", help="Execute the plan (default dry-run)"),
    base_url: str | None = typer.Option(None, "--base-url", envvar="OPTRO_BASE_URL"),
    token: str | None = typer.Option(None, "--token", envvar="OPTRO_TOKEN"),
    auth_header: str | None = typer.Option(None, "--auth-header", envvar="OPTRO_AUTH_HEADER"),
    auth_scheme: str | None = typer.Option("Bearer", "--auth-scheme", envvar="OPTRO_AUTH_SCHEME"),
    timeout_s: float | None = typer.Option(None, "--timeout"),
    insecure: bool = typer.Option(False, "--insecure"),
) -> None:
    client = _client(
        base_url=base_url,
        token=token,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        timeout_s=timeout_s,
        insecure=insecure,
        dry_run=not apply,
    )
    ops = json.loads(plan.read_text("utf-8"))
    if not isinstance(ops, list):
        raise typer.BadParameter("Plan file must be a JSON array.")
    for i, op in enumerate(ops, start=1):
        method = op.get("method")
        path = op.get("path")
        if not method or not path:
            raise typer.BadParameter("Each op must include method and path.")
        out = client.request_json(method, path, params=op.get("params"), json_body=op.get("json"))
        if client.dry_run:
            console.print(f"[dry-run] {i}/{len(ops)} {method} {path}")
        else:
            console.print(f"ran {i}/{len(ops)} {method} {path}")
            console.print(Pretty(out))


shadow_app = typer.Typer(help="Shadowing helpers (export/diff/apply) for users/allowed access lists.")
app.add_typer(shadow_app, name="shadow")


@shadow_app.command("export")
def shadow_export(
    out: Path = typer.Option(..., "--out", help="Write shadow snapshot JSON here"),
    base_url: str | None = typer.Option(None, "--base-url", envvar="OPTRO_BASE_URL"),
    token: str | None = typer.Option(None, "--token", envvar="OPTRO_TOKEN"),
    auth_header: str | None = typer.Option(None, "--auth-header", envvar="OPTRO_AUTH_HEADER"),
    auth_scheme: str | None = typer.Option("Bearer", "--auth-scheme", envvar="OPTRO_AUTH_SCHEME"),
    timeout_s: float | None = typer.Option(None, "--timeout"),
    insecure: bool = typer.Option(False, "--insecure"),
) -> None:
    """Export a minimal access 'shadow' snapshot you can compare between tenants."""
    client = _client(
        base_url=base_url,
        token=token,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        timeout_s=timeout_s,
        insecure=insecure,
        dry_run=False,
    )
    snapshot = {
        "users": client.request_json("GET", "/users"),
        "allowed_users": client.request_json("GET", "/allowed_users"),
        "allowed_teams": client.request_json("GET", "/allowed_teams"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    console.print(f"Wrote shadow snapshot to {out}")


@shadow_app.command("diff")
def shadow_diff(
    a: Path = typer.Option(..., "--a", exists=True),
    b: Path = typer.Option(..., "--b", exists=True),
) -> None:
    """Very simple diff: compares allowed_users/allowed_teams by raw JSON records."""
    obj_a = json.loads(a.read_text("utf-8"))
    obj_b = json.loads(b.read_text("utf-8"))

    def items(obj: Any, key: str) -> list[dict[str, Any]]:
        payload = obj.get(key, {})
        if isinstance(payload, dict) and key in ("users", "roles"):
            return payload.get(key, [])
        if isinstance(payload, dict):
            return payload.get(key, [])
        return []

    for key in ("allowed_users", "allowed_teams"):
        set_a = {json.dumps(x, sort_keys=True) for x in (obj_a.get(key, {}) or {}).get(key, [])}
        set_b = {json.dumps(x, sort_keys=True) for x in (obj_b.get(key, {}) or {}).get(key, [])}
        console.print(f"{key}: only-in-a={len(set_a-set_b)} only-in-b={len(set_b-set_a)}")


@shadow_app.command("plan")
def shadow_plan(
    source: Path = typer.Option(..., "--source", exists=True, help="Source snapshot (exported)"),
    target: Path = typer.Option(..., "--target", exists=True, help="Target snapshot (exported)"),
    out: Path = typer.Option(..., "--out", help="Write sandbox plan JSON here"),
) -> None:
    """
    Create a sandbox plan to add missing `allowed_users` / `allowed_teams` entries to the target.

    Apply via: `optro sandbox run --plan <out> --apply`.
    """
    src = json.loads(source.read_text("utf-8"))
    tgt = json.loads(target.read_text("utf-8"))

    def set_of(obj: Any, key: str, id_key: str) -> set[int]:
        payload = obj.get(key, {})
        items = (payload or {}).get(key, [])
        out_ids: set[int] = set()
        for it in items:
            if isinstance(it, dict) and isinstance(it.get(id_key), int):
                out_ids.add(int(it[id_key]))
        return out_ids

    src_allowed_users = set_of(src, "allowed_users", "user_id")
    tgt_allowed_users = set_of(tgt, "allowed_users", "user_id")
    src_allowed_teams = set_of(src, "allowed_teams", "team_id")
    tgt_allowed_teams = set_of(tgt, "allowed_teams", "team_id")

    ops: list[dict[str, Any]] = []
    for user_id in sorted(src_allowed_users - tgt_allowed_users):
        ops.append({"method": "POST", "path": "/allowed_users", "json": {"allowed_user": {"user_id": user_id}}})
    for team_id in sorted(src_allowed_teams - tgt_allowed_teams):
        ops.append({"method": "POST", "path": "/allowed_teams", "json": {"allowed_team": {"team_id": team_id}}})

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ops, indent=2) + "\n", encoding="utf-8")
    console.print(f"Wrote plan with {len(ops)} ops to {out}")


@access_app.command("analyze")
def access_analyze(
    snapshot: Path = typer.Option(..., "--snapshot", exists=True),
) -> None:
    """Analyze an access audit snapshot for quick findings."""
    obj = json.loads(snapshot.read_text("utf-8"))

    users = (obj.get("users") or {}).get("users", [])
    roles = (obj.get("roles") or {}).get("roles", [])
    allowed_users = (obj.get("allowed_users") or {}).get("allowed_users", [])
    allowed_teams = (obj.get("allowed_teams") or {}).get("allowed_teams", [])

    role_ids = {r.get("id") for r in roles if isinstance(r, dict)}
    users_missing_role = [
        u for u in users if isinstance(u, dict) and u.get("role_id") is not None and u.get("role_id") not in role_ids
    ]
    dup_allowed_users = len(allowed_users) - len(
        {u.get("user_id") for u in allowed_users if isinstance(u, dict) and u.get("user_id") is not None}
    )
    dup_allowed_teams = len(allowed_teams) - len(
        {t.get("team_id") for t in allowed_teams if isinstance(t, dict) and t.get("team_id") is not None}
    )

    console.print(
        {
            "users": len(users),
            "roles": len(roles),
            "allowed_users": len(allowed_users),
            "allowed_teams": len(allowed_teams),
            "users_with_unknown_role_id": len(users_missing_role),
            "duplicate_allowed_users_by_user_id": dup_allowed_users,
            "duplicate_allowed_teams_by_team_id": dup_allowed_teams,
        }
    )

spec_app = typer.Typer(help="Spec utilities (resolve local spec files).")
app.add_typer(spec_app, name="spec")


@spec_app.command("path")
def spec_path(
    version: str = typer.Argument(...),
    specs_dir: Path = typer.Option(Path("Local/OpenAPI Specs"), "--specs-dir"),
) -> None:
    p = resolve_spec_path(specs_dir, version)
    console.print(str(p))
