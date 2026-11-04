"""Tenant telemetry sinks. Locators are references, not secret values."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govagent.telemetry.exporters.azure import AzureMonitorExporter
from govagent.telemetry.exporters.cloudwatch import CloudWatchExporter
from govagent.telemetry.exporters.mock import MockSOCExporter

from govagent_platform.domain.models import TelemetrySink
from govagent_platform.security.context import Actor
from govagent_platform.services.audit import write_audit
from govagent_platform.services.errors import ServiceError

_TYPES = {"mock", "cloudwatch", "azure"}


def create_sink(session: Session, actor: Actor, *, sink_type: str, locator: str) -> TelemetrySink:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")
    kind = sink_type.strip().lower()
    if kind not in _TYPES:
        raise ServiceError(422, "sink_type must be mock, cloudwatch, or azure")
    if not locator or not locator.strip():
        raise ServiceError(422, "locator is required")
    row = TelemetrySink(tenant_id=actor.tenant_id, sink_type=kind, locator=locator.strip())
    session.add(row)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="sink.create",
        target_type="telemetry_sink",
        target_id=str(row.id),
        after={"sink_type": row.sink_type, "locator": row.locator},
        tenant_id=actor.tenant_id,
    )
    return row


def list_sinks(session: Session, actor: Actor) -> list[TelemetrySink]:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")
    return list(session.scalars(select(TelemetrySink).order_by(TelemetrySink.created_at)).all())


def sink_payload(row: TelemetrySink) -> dict:
    return {
        "id": str(row.id),
        "sink_type": row.sink_type,
        "locator": row.locator,
    }


def exporter_for_sink(row: TelemetrySink):
    """Build a library exporter only when the locator can be used.

    Cloud and Azure clients are constructed only when credentials are present.
    A missing credential skips the sink instead of failing the evaluate call.
    """

    if row.sink_type == "mock":
        return MockSOCExporter()
    if row.sink_type == "cloudwatch" and os.environ.get("AWS_ACCESS_KEY_ID") and row.locator:
        return CloudWatchExporter(log_group=row.locator)
    if (
        row.sink_type == "azure"
        and row.locator
        and os.environ.get("AZURE_CLIENT_ID")
        and os.environ.get("DATA_COLLECTION_ENDPOINT")
        and os.environ.get("LOGS_DCR_RULE_ID")
    ):
        return AzureMonitorExporter()
    return None


async def fanout_sinks(session: Session, snapshot_data: dict[str, Any]) -> None:
    rows = list(session.scalars(select(TelemetrySink)).all())
    for row in rows:
        try:
            exporter = exporter_for_sink(row)
            if exporter is None:
                continue
            await exporter.export(snapshot_data)
        except Exception:
            continue
