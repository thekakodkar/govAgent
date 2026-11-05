"""Platform tests run only when PLATFORM_TEST_DATABASE_URL points at real Postgres.

Collection is ignored when that variable is unset so the library suite stays at
21 passed and 1 skipped.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

def _locate_roots() -> tuple[Path, Path, Path | None]:
    """Monorepo today, platform repo root after tests/platform is moved to tests/."""

    for parent in Path(__file__).resolve().parents:
        if (parent / "platform" / "govagent_platform").is_dir() and (parent / "src" / "govagent").is_dir():
            return parent, parent / "platform", parent / "src"
        if (parent / "govagent_platform").is_dir() and (parent / "alembic.ini").is_file():
            return parent, parent, None
    raise RuntimeError("govagent-platform root was not found")


_REPO_ROOT, _PLATFORM_ROOT, _SRC_ROOT = _locate_roots()
for _path in (_REPO_ROOT, _PLATFORM_ROOT, _SRC_ROOT):
    if _path is not None and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

def pytest_ignore_collect(collection_path, config):  # noqa: ARG001
    if os.environ.get("PLATFORM_TEST_DATABASE_URL"):
        return None
    return True


@pytest.fixture(scope="session")
def platform_database():
    test_url = os.environ.get("PLATFORM_TEST_DATABASE_URL", "").strip()
    admin_url = os.environ.get("PLATFORM_DATABASE_URL", "").strip()
    if not test_url or not admin_url:
        pytest.skip("PLATFORM_TEST_DATABASE_URL and PLATFORM_DATABASE_URL are required")

    os.environ["PLATFORM_APP_DATABASE_URL"] = os.environ.get(
        "PLATFORM_APP_DATABASE_URL", test_url
    ).strip() or test_url
    os.environ.setdefault("PLATFORM_SESSION_SECRET", "test-session-secret")
    os.environ.setdefault("PLATFORM_ENVIRONMENT", "test")

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    platform_root = _PLATFORM_ROOT
    cfg = Config(str(platform_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(platform_root / "migrations"))

    admin = create_engine(admin_url, pool_pre_ping=True, future=True)
    last_error: Exception | None = None
    for _ in range(30):
        try:
            with admin.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except Exception as exc:  # connection refused while Postgres starts
            last_error = exc
            time.sleep(1)
    else:
        pytest.fail(f"Postgres is not reachable at PLATFORM_DATABASE_URL: {last_error}")

    command.upgrade(cfg, "head")

    from sqlalchemy.pool import NullPool

    app_engine = create_engine(test_url, pool_pre_ping=True, poolclass=NullPool, future=True)
    with app_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT current_user AS name, rolsuper, rolbypassrls
                FROM pg_roles
                WHERE rolname = current_user
                """
            )
        ).one()
    if row.rolsuper or row.rolbypassrls:
        pytest.fail(
            f"{row.name} bypasses row-level security. "
            "PLATFORM_TEST_DATABASE_URL must be the govagent_app role."
        )
    yield {"admin": admin, "app": app_engine}
    app_engine.dispose()
    admin.dispose()


@pytest.fixture
def session(platform_database):
    from sqlalchemy.orm import Session

    from govagent_platform.db import begin_platform

    connection = platform_database["app"].connect()
    transaction = connection.begin()
    db = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    begin_platform(db)
    try:
        yield db
    finally:
        db.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def world(session):
    from sqlalchemy import select

    from govagent_platform.db import begin_platform
    from govagent_platform.domain.models import (
        Identity,
        MembershipRole,
        Plan,
        PlatformRoleBinding,
        Role,
        Tenant,
        TenantMembership,
    )
    from govagent_platform.security.context import Actor
    from govagent_platform.security.passwords import hash_password
    from tests.platform.accounts import (
        ALPHA_ADMIN_EMAIL,
        ALPHA_ADMIN_PASSWORD,
        AUDITOR_EMAIL,
        AUDITOR_PASSWORD,
        BETA_ADMIN_EMAIL,
        BETA_ADMIN_PASSWORD,
        OPERATOR_EMAIL,
        OPERATOR_PASSWORD,
    )

    begin_platform(session)
    plan = session.scalar(select(Plan).where(Plan.code == "community"))
    assert plan is not None
    operator_role = session.scalar(
        select(Role).where(Role.scope == "platform", Role.code == "operator")
    )
    admin_role = session.scalar(
        select(Role).where(Role.scope == "tenant", Role.code == "tenant_admin")
    )
    auditor_role = session.scalar(
        select(Role).where(Role.scope == "tenant", Role.code == "tenant_auditor")
    )
    assert operator_role and admin_role and auditor_role

    def identity(email: str, password: str, name: str) -> Identity:
        row = Identity(
            email=email,
            display_name=name,
            password_hash=hash_password(password),
            status="active",
        )
        session.add(row)
        session.flush()
        return row

    operator = identity(OPERATOR_EMAIL, OPERATOR_PASSWORD, "Operator")
    alpha_admin = identity(ALPHA_ADMIN_EMAIL, ALPHA_ADMIN_PASSWORD, "Alpha Admin")
    beta_admin = identity(BETA_ADMIN_EMAIL, BETA_ADMIN_PASSWORD, "Beta Admin")
    auditor = identity(AUDITOR_EMAIL, AUDITOR_PASSWORD, "Alpha Auditor")
    session.add(PlatformRoleBinding(identity_id=operator.id, role_id=operator_role.id))

    alpha = Tenant(
        slug="alpha",
        display_name="Alpha",
        status="active",
        plan_id=plan.id,
        isolation_tier="shared",
        region="local",
    )
    beta = Tenant(
        slug="beta",
        display_name="Beta",
        status="active",
        plan_id=plan.id,
        isolation_tier="shared",
        region="local",
    )
    session.add_all([alpha, beta])
    session.flush()

    def bind(tenant: Tenant, person: Identity, role: Role) -> None:
        session.add(
            TenantMembership(tenant_id=tenant.id, identity_id=person.id, status="active")
        )
        session.flush()
        session.add(
            MembershipRole(
                tenant_id=tenant.id,
                identity_id=person.id,
                role_id=role.id,
            )
        )

    bind(alpha, alpha_admin, admin_role)
    bind(beta, beta_admin, admin_role)
    bind(alpha, auditor, auditor_role)
    session.flush()

    actor = Actor(
        identity_id=operator.id,
        scope="platform",
        tenant_id=None,
        permissions=frozenset(),
    )
    return SimpleNamespace(
        operator=operator,
        alpha_admin=alpha_admin,
        beta_admin=beta_admin,
        auditor=auditor,
        alpha=alpha,
        beta=beta,
        plan=plan,
        actor=actor,
    )


@pytest.fixture
def client(session, world):
    from fastapi.testclient import TestClient

    from govagent_platform.api.main import create_app
    from govagent_platform.config import clear_settings_cache
    from govagent_platform.db import reset_engine
    from govagent_platform.security.dependencies import get_db

    clear_settings_cache()
    reset_engine()
    app = create_app()

    def override():
        yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as test_client:
        yield test_client
    clear_settings_cache()
    reset_engine()
