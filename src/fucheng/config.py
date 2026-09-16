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

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.getenv("FUCHENG_DATABASE_URL", "sqlite:///data/fucheng.db")
        return cls(
            database_url=database_url,
            session_cookie_secure=os.getenv("FUCHENG_COOKIE_SECURE", "true").lower()
            in {"1", "true", "yes"},
            session_hours=int(os.getenv("FUCHENG_SESSION_HOURS", "12")),
            static_dir=Path(os.getenv("FUCHENG_STATIC_DIR", Path(__file__).parent / "static")),
        )
