"""Persist a library telemetry dump through BaseExporter. Tenant id stays a SQL column."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from govagent.telemetry.exporters.base import BaseExporter

from govagent_platform.domain.models import ExecutionSnapshotRow, FiscalLedgerEntry


class TenantDatabaseExporter(BaseExporter):
    def __init__(self, session, tenant_id: UUID, agent_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.incremental_steps: list[float] = []
        self.approval_request_id: str | None = None
        self.model_name: str | None = None
        self.tokens: int | None = None

    async def export(self, snapshot_data: dict[str, Any]) -> bool:
        trace_id = str(snapshot_data.get("trace_id"))
        self.session.add(
            ExecutionSnapshotRow(
                tenant_id=self.tenant_id,
                trace_id=trace_id,
                parent_trace_id=snapshot_data.get("parent_trace_id"),
                agent_id=self.agent_id,
                status=str(snapshot_data.get("status") or "error"),
                task_input=snapshot_data.get("task_input"),
                metrics={
                    "library": snapshot_data,
                    "incremental_costs": self.incremental_steps,
                    "approval_request_id": self.approval_request_id,
                    "model": self.model_name,
                },
                guards_evaluated=list(snapshot_data.get("guards_evaluated") or []),
            )
        )
        for amount in self.incremental_steps:
            self.session.add(
                FiscalLedgerEntry(
                    tenant_id=self.tenant_id,
                    trace_id=trace_id,
                    amount_usd=Decimal(str(amount)),
                    model=self.model_name,
                    tokens=self.tokens,
                )
            )
        self.session.flush()
        return True
