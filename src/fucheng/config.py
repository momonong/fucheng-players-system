from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    session_cookie_secure: bool = True
    session_hours: int = 12
    static_dir: Path = Path(__file__).parent / "static"
    public_origin: str | None = None
    trusted_proxy: str | None = None
    proxy_kind: str = "local"
    local_http_preview: bool = False

    def __post_init__(self):
        if self.public_origin or self.local_http_preview:
            from .proxy import validate_ingress
            validate_ingress(self)

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.getenv("FUCHENG_DATABASE_URL", "sqlite:///data/fucheng.db")
        return cls(
            database_url=database_url,
            session_cookie_secure=os.getenv("FUCHENG_COOKIE_SECURE", "true").lower()
            in {"1", "true", "yes"},
            session_hours=int(os.getenv("FUCHENG_SESSION_HOURS", "12")),
            static_dir=Path(os.getenv("FUCHENG_STATIC_DIR", Path(__file__).parent / "static")),
            public_origin=os.getenv("FUCHENG_PUBLIC_ORIGIN") or None,
            trusted_proxy=os.getenv("FUCHENG_TRUSTED_PROXY") or None,
            proxy_kind=os.getenv("FUCHENG_PROXY_KIND", "local"),
            local_http_preview=os.getenv("FUCHENG_LOCAL_HTTP_PREVIEW", "false").lower() == "true",
        )
