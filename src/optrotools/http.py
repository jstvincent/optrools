from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

import requests

from .config import OptroConfig


@dataclass(frozen=True)
class PlannedRequest:
    method: str
    url: str
    params: Mapping[str, Any] | None
    json_body: Any | None

    def to_curl(self) -> str:
        parts = ["curl", "-sS", "-X", self.method.upper(), json.dumps(self.url)]
        if self.params:
            # best-effort: encode as query string by letting curl send full URL; keep params in output for readability
            parts.append("# params: " + json.dumps(dict(self.params)))
        if self.json_body is not None:
            parts.extend(["-H", json.dumps("Content-Type: application/json"), "-d", json.dumps(self.json_body)])
        return " ".join(parts)


class OptroClient:
    def __init__(self, cfg: OptroConfig, *, dry_run: bool = False) -> None:
        self._cfg = cfg
        self._dry_run = dry_run
        self._session = requests.Session()

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._cfg.token:
            if self._cfg.auth_scheme:
                headers[self._cfg.auth_header] = f"{self._cfg.auth_scheme} {self._cfg.token}"
            else:
                headers[self._cfg.auth_header] = self._cfg.token
        return headers

    def plan(self, method: str, path_or_url: str, *, params: Mapping[str, Any] | None, json_body: Any | None) -> PlannedRequest:
        url = path_or_url
        if not url.startswith("http"):
            if not url.startswith("/"):
                url = "/" + url
            prefix = self._cfg.api_prefix or ""
            # Avoid doubling the prefix if the caller already included it.
            if prefix and url.startswith(prefix + "/"):
                full_path = url
            elif prefix and url == prefix:
                full_path = url
            elif prefix:
                full_path = f"{prefix}{url}"
            else:
                full_path = url
            url = f"{self._cfg.base_url}{full_path}"
        return PlannedRequest(method=method, url=url, params=params, json_body=json_body)

    def request_json(
        self,
        method: str,
        path_or_url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> Any:
        planned = self.plan(method, path_or_url, params=params, json_body=json_body)
        if self._dry_run:
            return {"dry_run": True, "planned": planned.__dict__}

        resp = self._session.request(
            method=planned.method.upper(),
            url=planned.url,
            headers=self._headers(),
            params=dict(planned.params) if planned.params else None,
            json=planned.json_body,
            timeout=self._cfg.timeout_s,
            verify=self._cfg.verify_tls,
        )
        resp.raise_for_status()
        if not resp.content:
            return None
        # best-effort JSON parsing
        ctype = resp.headers.get("content-type", "")
        if "text/html" in ctype:
            raise RuntimeError(
                "Server returned HTML instead of JSON. This often means your base URL is missing the API prefix.\n"
                f"Current: OPTRO_BASE_URL={self._cfg.base_url!r} OPTRO_API_PREFIX={self._cfg.api_prefix!r}\n"
                "Try setting OPTRO_API_PREFIX (commonly /api/v1) or include it in OPTRO_BASE_URL."
            )
        if "application/json" in ctype or ctype.endswith("+json") or ctype == "":
            return resp.json()
        return {"content_type": ctype, "text": resp.text}

    def download_to_path(self, url: str, out_path: str) -> None:
        if self._dry_run:
            return
        with self._session.get(url, headers=self._headers(), timeout=self._cfg.timeout_s, verify=self._cfg.verify_tls, stream=True) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
