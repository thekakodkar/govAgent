from __future__ import annotations

import contextvars

from pydantic import BaseModel


class FiscalStateSnapshot(BaseModel):
    """Immutable representation of live swarm resource matrices to avoid async bleeding."""

    cumulative_spend: float = 0.0
    task_counter: int = 0


_shared_spend: contextvars.ContextVar[FiscalStateSnapshot] = contextvars.ContextVar("shared_spend")


def _blank_snapshot() -> FiscalStateSnapshot:
    return FiscalStateSnapshot(cumulative_spend=0.0, task_counter=0)


def _current_snapshot() -> FiscalStateSnapshot:
    try:
        return _shared_spend.get()
    except LookupError:
        snapshot = _blank_snapshot()
        _shared_spend.set(snapshot)
        return snapshot


def reset_fiscal_ledger() -> None:
    """Institutional Cleanup: Atomically resets the shared spend matrices back to baseline."""
    _shared_spend.set(_blank_snapshot())


def get_shared_fiscal_metrics() -> dict[str, float]:
    """Retrieves standard flat metric maps for cascading circuit breakers."""
    state = _current_snapshot()
    return {
        "cumulative_spend": state.cumulative_spend,
        "task_counter": float(state.task_counter),
    }


def update_shared_spend(amount: float) -> None:
    """
    Atomically updates aggregate swarm expenditures.
    Generates a fresh state snapshot out-of-band to guarantee thread-safe isolation.
    """
    current_snapshot = _current_snapshot()
    updated_snapshot = FiscalStateSnapshot(
        cumulative_spend=round(current_snapshot.cumulative_spend + amount, 6),
        task_counter=current_snapshot.task_counter + 1,
    )
    _shared_spend.set(updated_snapshot)
