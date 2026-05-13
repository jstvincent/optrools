from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class OptroConfig:
    base_url: str
    api_prefix: str
    token: str | None
    auth_header: str
    auth_scheme: str | None
    timeout_s: float
    verify_tls: bool


def load_config(
    *,
    base_url: str | None,
    api_prefix: str | None,
    token: str | None,
    auth_header: str | None,
    auth_scheme: str | None,
    timeout_s: float | None,
    verify_tls: bool | None,
) -> OptroConfig:
    resolved_base_url = (base_url or os.getenv("OPTRO_BASE_URL") or "").strip()
    if not resolved_base_url:
        raise ValueError("Missing base URL. Set `--base-url` or OPTRO_BASE_URL.")

    resolved_token = (token if token is not None else os.getenv("OPTRO_TOKEN")) or None
    resolved_auth_header = (auth_header or os.getenv("OPTRO_AUTH_HEADER") or "Authorization").strip()
    resolved_auth_scheme = (
        auth_scheme if auth_scheme is not None else os.getenv("OPTRO_AUTH_SCHEME", "Bearer")
    )
    resolved_api_prefix = (
        api_prefix
        if api_prefix is not None
        else os.getenv("OPTRO_API_PREFIX", "/api/v1")
    ).strip()
    if resolved_api_prefix in ("/", ""):
        resolved_api_prefix = ""
    if resolved_api_prefix and not resolved_api_prefix.startswith("/"):
        resolved_api_prefix = "/" + resolved_api_prefix
    resolved_api_prefix = resolved_api_prefix.rstrip("/")
    resolved_timeout = float(timeout_s if timeout_s is not None else os.getenv("OPTRO_TIMEOUT_S", "60"))
    resolved_verify = bool(
        verify_tls if verify_tls is not None else os.getenv("OPTRO_VERIFY_TLS", "true").lower() != "false"
    )

    return OptroConfig(
        base_url=resolved_base_url.rstrip("/"),
        api_prefix=resolved_api_prefix,
        token=resolved_token,
        auth_header=resolved_auth_header,
        auth_scheme=resolved_auth_scheme,
        timeout_s=resolved_timeout,
        verify_tls=resolved_verify,
    )
