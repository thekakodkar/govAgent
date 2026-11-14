from __future__ import annotations

import json
import os
import uuid
from typing import Any

from pydantic import BaseModel, Field

from govagent.telemetry.exporters.jsonl import JsonlFileExporter
from govagent.telemetry.otel import end_execute_span, start_execute_span


def _audit_disabled() -> bool:
    return os.environ.get("GOVAGENT_DISABLE_AUDIT_LOG", "").strip().lower() in {"1", "true", "yes"}


class ExecutionSnapshot(BaseModel):
    """Forensic Data Model with Article 12 Traceability."""

    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_trace_id: str | None = None
    agent_id: str
    task_input: str
    status: str = "pending"
    estimated_cost_usd: float = 0.0
    recursive_tco_usd: float = 0.0
    guards_evaluated: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)


class TelemetryManager:
    """Forensic Evidence Engine with a default JSONL ledger and optional OTel spans."""

    def __init__(
        self,
        buffer_path: str = "logs/audit_buffer.jsonl",
        *,
        audit_path: str | None = None,
        persist_jsonl: bool | None = None,
    ):
        self.exporters: list[Any] = []
        self.current_session: ExecutionSnapshot | None = None
        self.buffer_path = buffer_path
        buffer_dir = os.path.dirname(self.buffer_path)
        if buffer_dir:
            os.makedirs(buffer_dir, exist_ok=True)
        self._otel_span: Any = None

        if persist_jsonl is None:
            persist_jsonl = not _audit_disabled()
        if persist_jsonl:
            path = audit_path or os.environ.get("GOVAGENT_AUDIT_LOG", "logs/audit_trail.jsonl")
            self.add_exporter(JsonlFileExporter(path))

    def add_exporter(self, exporter: Any) -> None:
        """Restores the Cloud SOC sink registration capability."""
        self.exporters.append(exporter)

    def start_trace(self, agent_id: str, task: str, parent_id: str | None = None) -> str:
        """
        Initiates a forensic record.
        Auto-inherits parent context if present to satisfy Article 12.
        """
        from govagent.context import get_current_agent, get_shared_fiscal_metrics

        if not parent_id:
            parent_agent = get_current_agent()
            if parent_agent and parent_agent.telemetry.current_session:
                parent_id = parent_agent.telemetry.current_session.trace_id

        self.current_session = ExecutionSnapshot(
            agent_id=agent_id,
            task_input=task,
            parent_trace_id=parent_id,
            recursive_tco_usd=get_shared_fiscal_metrics().get("cumulative_spend", 0.0),
        )
        self._otel_span = start_execute_span(
            agent_id=agent_id,
            trace_id=self.current_session.trace_id,
        )
        return self.current_session.trace_id

    def log_step(self, thought: str, action: str, result: str) -> None:
        if self.current_session:
            self.current_session.steps.append({"thought": thought, "action": action, "result": result})

    def record_guard(self, name: str) -> None:
        if self.current_session and name not in self.current_session.guards_evaluated:
            self.current_session.guards_evaluated.append(name)

    async def finalize(self, status: str = "success", tokens: int = 0) -> ExecutionSnapshot | None:
        if not self.current_session:
            return None
        self.current_session.status = status

        snapshot = self.current_session.model_dump()
        for exporter in self.exporters:
            try:
                await exporter.export(snapshot)
            except Exception as exc:  # noqa: BLE001 - fail over to the DLQ
                self._buffer_to_dlq(snapshot, str(exc))

        end_execute_span(
            self._otel_span,
            status=status,
            tokens=tokens,
            cost_usd=self.current_session.estimated_cost_usd,
        )
        self._otel_span = None
        return self.current_session

    def _buffer_to_dlq(self, snapshot: dict[str, Any], error: str) -> None:
        snapshot["governance_error"] = error
        with open(self.buffer_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, default=str) + "\n")
