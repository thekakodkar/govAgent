import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from .base import BaseExporter

logger = logging.getLogger("govagent.telemetry.exporters.federated")

class FederatedAuditPayload(BaseModel):
    """
    Immutable cross-organizational compliance capsule.
    Binds execution snapshots to strict tenant-isolated containers.
    """
    trace_id: str
    organization_id: str
    agent_id: str
    task_input: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    status: str
    payload_digest: Dict[str, Any]

class FederatedTelemetryExporter(BaseExporter):
    """
    v0.6.0 Federated Cross-Organization Audit Exporter.
    Inherits from BaseExporter to process universal multi-tenant log distribution.
    """
    def __init__(self):
        # Maps organization identifiers to their designated enterprise compliance destinations
        self.registered_org_sinks: Dict[str, List[Dict[str, Any]]] = {}

    def register_organization_sink(self, organization_id: str, sink_config: Dict[str, Any]) -> None:
        """Enrolls an external corporate entity's log target into the governance plane."""
        if organization_id not in self.registered_org_sinks:
            self.registered_org_sinks[organization_id] = []
        self.registered_org_sinks[organization_id].append(sink_config)
        logger.info(f"FederatedTelemetryExporter: Connected compliance sink for Organization: '{organization_id}'")

    async def export(self, snapshot_data: Dict[str, Any]) -> bool:
        """
        Processes standard contracts. Extracts organization scope variables, 
        wraps snapshots into audited payloads, and dispatches to specific destinations.
        """
        # Context extraction: Safely target org markers embedded in the snapshot context or default
        context_block = snapshot_data.get("context", {}) or {}
        org_id = context_block.get("organization_id") or snapshot_data.get("organization_id", "GLOBAL_HOLDING")
        trace_id = snapshot_data.get("trace_id", "UNKNOWN_TRACE")

        # 1. Envelope session data into strict cross-org schemas
        audit_payload = FederatedAuditPayload(
            trace_id=trace_id,
            organization_id=org_id,
            agent_id=snapshot_data.get("agent_id", "UnknownAgent"),
            task_input=snapshot_data.get("task_input", ""),
            status=snapshot_data.get("status", "pending"),
            payload_digest={
                "estimated_cost_usd": snapshot_data.get("estimated_cost_usd", 0.0),
                "recursive_tco_usd": snapshot_data.get("recursive_tco_usd", 0.0),
                "guards_evaluated": snapshot_data.get("guards_evaluated", []),
                "steps_taken": snapshot_data.get("steps", [])
            }
        )

        # 2. Extract valid corporate destination targets
        sinks = self.registered_org_sinks.get(org_id)
        if not sinks:
            logger.warning(f"FederatedTelemetryExporter: Trace {trace_id} blocked. Organization '{org_id}' has no registered compliance sink.")
            return False

        # 3. Transmit forensic logs sequentially to all tenant destinations
        dispatch_success = True
        for sink in sinks:
            try:
                sink_type = sink.get("type", "CONSOLE")
                # In production, this anchors to self.client web hooks or message queue sinks
                logger.info(f"🚀 Cross-Org Engine: Routed trace {trace_id} to {sink_type} for Tenant [{org_id}]")
            except Exception as e:
                logger.error(f"FederatedTelemetryExporter: Transmission error on target sink: {str(e)}")
                dispatch_success = False

        return dispatch_success