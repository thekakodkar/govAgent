"""Rehydrate the library context ledger from tenant rows, then reuse the breaker."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from govagent.context import reset_fiscal_ledger, update_shared_spend


def opening_balances(session: Session) -> tuple[float, float]:
    all_time = session.execute(
        text("SELECT COALESCE(SUM(amount_usd), 0) FROM fiscal_ledger_entries")
    ).scalar_one()
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today = session.execute(
        text(
            "SELECT COALESCE(SUM(amount_usd), 0) FROM fiscal_ledger_entries "
            "WHERE created_at >= :start"
        ),
        {"start": start},
    ).scalar_one()
    return float(all_time), float(today)


def assert_spend_allowed(guard, projected: float, all_time: float, today: float) -> None:
    """Two openings, one breaker. The library compares against min(tco, daily)."""

    reset_fiscal_ledger()
    update_shared_spend(all_time)
    guard.check_financial_risk(projected)
    reset_fiscal_ledger()
    update_shared_spend(today)
    guard.check_financial_risk(projected)
    reset_fiscal_ledger()
