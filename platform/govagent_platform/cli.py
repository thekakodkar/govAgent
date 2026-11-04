"""One-shot operator bootstrap.

Password is read from the terminal. It is not accepted as an argument.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from govagent_platform.config import SettingsError, get_settings
from govagent_platform.db import begin_platform
from govagent_platform.domain.models import Identity, PlatformRoleBinding, Role
from govagent_platform.security.passwords import hash_password


class BootstrapError(RuntimeError):
    pass


def _bootstrap(session: Session, email: str, password: str, *, commit: bool) -> Identity:
    begin_platform(session)
    existing = session.scalar(
        select(PlatformRoleBinding.identity_id)
        .join(Role, Role.id == PlatformRoleBinding.role_id)
        .where(Role.scope == "platform", Role.code == "operator")
        .limit(1)
    )
    if existing is not None:
        raise BootstrapError("An operator binding already exists")
    role = session.scalar(
        select(Role).where(Role.scope == "platform", Role.code == "operator", Role.tenant_id.is_(None))
    )
    if role is None:
        raise BootstrapError("Operator role is not seeded; run migrations first")
    normalized = email.strip().lower()
    if "@" not in normalized:
        raise BootstrapError("Email is invalid")
    identity = Identity(
        email=normalized,
        display_name=normalized,
        password_hash=hash_password(password),
        status="active",
    )
    session.add(identity)
    session.flush()
    session.add(PlatformRoleBinding(identity_id=identity.id, role_id=role.id))
    session.flush()
    if commit:
        session.commit()
    return identity


def bootstrap_operator(email: str, password: str, session: Session | None = None) -> Identity:
    if session is not None:
        return _bootstrap(session, email, password, commit=False)
    try:
        settings = get_settings(require_secret=False)
    except SettingsError as exc:
        raise BootstrapError(str(exc)) from exc
    if not settings.app_database_url:
        raise BootstrapError("PLATFORM_APP_DATABASE_URL is required")

    engine = create_engine(settings.app_database_url, future=True)
    owned = Session(engine, future=True)
    try:
        return _bootstrap(owned, email, password, commit=True)
    except Exception:
        owned.rollback()
        raise
    finally:
        owned.close()
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="govagent_platform.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    boot = sub.add_parser("bootstrap-operator")
    boot.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    if args.command != "bootstrap-operator":
        return 2
    if not sys.stdin.isatty():
        print("Password must be entered on a terminal, not via arguments.", file=sys.stderr)
        return 2
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 2
    try:
        identity = bootstrap_operator(args.email, password)
    except (BootstrapError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Operator created: {identity.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
