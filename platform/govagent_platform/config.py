"""Process settings. The API refuses to start without a database URL and session secret."""

from __future__ import annotations

import os
from dataclasses import dataclass


class SettingsError(RuntimeError):
    """Raised when required platform configuration is absent."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_database_url: str
    session_secret: str
    environment: str


_cached: Settings | None = None


def clear_settings_cache() -> None:
    global _cached
    _cached = None


def get_settings(*, require_secret: bool = True) -> Settings:
    """Load settings from the environment.

    ``require_secret`` is true for the API. The operator bootstrap CLI only
    needs the database URLs.
    """

    global _cached
    if _cached is not None and (not require_secret or _cached.session_secret):
        return _cached

    database_url = os.environ.get("PLATFORM_DATABASE_URL", "").strip()
    app_database_url = os.environ.get("PLATFORM_APP_DATABASE_URL", "").strip()
    session_secret = os.environ.get("PLATFORM_SESSION_SECRET", "").strip()
    environment = os.environ.get("PLATFORM_ENVIRONMENT", "local").strip() or "local"

    missing = []
    if not database_url:
        missing.append("PLATFORM_DATABASE_URL")
    if not app_database_url:
        missing.append("PLATFORM_APP_DATABASE_URL")
    if require_secret and not session_secret:
        missing.append("PLATFORM_SESSION_SECRET")
    if missing:
        raise SettingsError(
            "Missing required platform settings: " + ", ".join(missing)
        )

    settings = Settings(
        database_url=database_url,
        app_database_url=app_database_url,
        session_secret=session_secret,
        environment=environment,
    )
    if require_secret:
        _cached = settings
    return settings
