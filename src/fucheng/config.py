from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    session_cookie_secure: bool = True
    session_hours: int = 12
    static_dir: Path = Path(__file__).parent / "static"
    data_dir: Path | None = None
    public_origin: str | None = None
    trusted_proxy: str | None = None
    proxy_kind: str = "local"
    local_http_preview: bool = False
    turnstile_mode: str = "disabled"
    turnstile_sitekey: str | None = None
    turnstile_secret: str | None = field(default=None, repr=False)
    turnstile_hostname: str | None = None
    backup_status_file: Path | None = None

    def __post_init__(self):
        if self.public_origin or self.local_http_preview:
            from .proxy import validate_ingress
            validate_ingress(self)
        if self.turnstile_mode not in {"disabled", "enabled"}:
            raise ValueError("Turnstile mode must be explicitly disabled or enabled")
        if self.proxy_kind == "cloudflare" and self.public_origin and not self.local_http_preview and self.turnstile_mode != "enabled":
            raise ValueError("Cloudflare deployment requires Turnstile enabled")
        if self.turnstile_mode == "enabled":
            hostname = self.turnstile_hostname or urlsplit(self.public_origin or "").hostname
            if not self.turnstile_sitekey or not self.turnstile_secret or not hostname:
                raise ValueError("Turnstile enabled requires sitekey, secret, and exact hostname")
            if self.public_origin and hostname != urlsplit(self.public_origin).hostname:
                raise ValueError("Turnstile hostname must match the public origin")

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.getenv("FUCHENG_DATABASE_URL", "sqlite:///data/fucheng.db")
        secret_file = os.getenv("FUCHENG_TURNSTILE_SECRET_FILE")
        if secret_file and os.getenv("FUCHENG_TURNSTILE_SECRET"):
            raise ValueError("Choose one Turnstile secret source")
        turnstile_secret = (Path(secret_file).read_text(encoding="utf-8").strip() if secret_file
                            else os.getenv("FUCHENG_TURNSTILE_SECRET"))
        return cls(
            database_url=database_url,
            session_cookie_secure=os.getenv("FUCHENG_COOKIE_SECURE", "true").lower()
            in {"1", "true", "yes"},
            session_hours=int(os.getenv("FUCHENG_SESSION_HOURS", "12")),
            static_dir=Path(os.getenv("FUCHENG_STATIC_DIR", Path(__file__).parent / "static")),
            data_dir=Path(os.environ["FUCHENG_DATA_DIR"]) if os.getenv("FUCHENG_DATA_DIR") else None,
            public_origin=os.getenv("FUCHENG_PUBLIC_ORIGIN") or None,
            trusted_proxy=os.getenv("FUCHENG_TRUSTED_PROXY") or None,
            proxy_kind=os.getenv("FUCHENG_PROXY_KIND", "local"),
            local_http_preview=os.getenv("FUCHENG_LOCAL_HTTP_PREVIEW", "false").lower() == "true",
            turnstile_mode=os.getenv("FUCHENG_TURNSTILE_MODE", "disabled"),
            turnstile_sitekey=os.getenv("FUCHENG_TURNSTILE_SITEKEY") or None,
            turnstile_secret=turnstile_secret or None,
            turnstile_hostname=os.getenv("FUCHENG_TURNSTILE_HOSTNAME") or None,
            backup_status_file=Path(os.environ["FUCHENG_BACKUP_STATUS_FILE"]) if os.getenv("FUCHENG_BACKUP_STATUS_FILE") else None,
        )
