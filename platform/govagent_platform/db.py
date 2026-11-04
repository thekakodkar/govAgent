"""Engine helpers and transaction-local tenant settings.

``SET LOCAL`` is issued through ``set_config(..., true)`` so a pooled connection
cannot keep another tenant's identifier after commit or rollback.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from govagent_platform.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.app_database_url, pool_pre_ping=True, future=True)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def _set(session: Session, key: str, value: str) -> None:
    session.execute(
        text("SELECT set_config(:key, :value, true)"),
        {"key": key, "value": value},
    )


def begin_platform(session: Session, *, break_glass: bool = False) -> None:
    """Operator scope. Payload tables stay hidden unless break-glass is on."""

    _set(session, "app.actor_scope", "platform")
    _set(session, "app.tenant_id", "")
    _set(session, "app.platform_break_glass", "on" if break_glass else "off")


def begin_tenant(session: Session, tenant_id: UUID) -> None:
    """Tenant scope. ``app.tenant_id`` is the only tenant the statement can see."""

    _set(session, "app.actor_scope", "tenant")
    _set(session, "app.tenant_id", str(tenant_id))
    _set(session, "app.platform_break_glass", "off")


def begin_authenticate(session: Session) -> None:
    """Login-only scope used to read memberships before a tenant is chosen.

    It is not a cookie scope and the policies do not let it write.
    """

    _set(session, "app.actor_scope", "authenticate")
    _set(session, "app.tenant_id", "")
    _set(session, "app.platform_break_glass", "off")
