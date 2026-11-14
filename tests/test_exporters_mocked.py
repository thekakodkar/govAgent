from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from govagent.pricing import PricingEngine
from govagent.telemetry.exporters.azure import AzureMonitorExporter
from govagent.telemetry.exporters.cloudwatch import CloudWatchExporter
from govagent.telemetry.exporters.jsonl import JsonlFileExporter
from govagent.telemetry.exporters.mock import MockSOCExporter


class _AlreadyExists(Exception):
    pass


def _logs_client() -> MagicMock:
    client = MagicMock()
    client.exceptions.ResourceAlreadyExistsException = _AlreadyExists
    return client


def test_cloudwatch_creates_log_group_and_exports(monkeypatch):
    client = _logs_client()
    with patch("govagent.telemetry.exporters.cloudwatch.boto3.client", return_value=client):
        exporter = CloudWatchExporter(log_group="/ga/test", log_stream="s1")
    client.create_log_group.assert_called_once_with(logGroupName="/ga/test")

    async def _run():
        assert await exporter.export({"trace_id": "t1", "status": "success"}) is True

    import asyncio

    asyncio.run(_run())
    client.put_log_events.assert_called_once()
    kwargs = client.put_log_events.call_args.kwargs
    assert kwargs["logGroupName"] == "/ga/test"
    assert kwargs["logStreamName"] == "s1"
    assert "t1" in kwargs["logEvents"][0]["message"]


def test_cloudwatch_swallows_existing_group_and_failed_export():
    client = _logs_client()
    client.create_log_group.side_effect = _AlreadyExists()
    client.put_log_events.side_effect = RuntimeError("throttle")
    with patch("govagent.telemetry.exporters.cloudwatch.boto3.client", return_value=client):
        exporter = CloudWatchExporter()

    import asyncio

    assert asyncio.run(exporter.export({"ok": True})) is False


@pytest.mark.asyncio
async def test_azure_exporter_upload_and_failure(monkeypatch):
    cred = MagicMock()
    logs = MagicMock()
    monkeypatch.setenv("DATA_COLLECTION_ENDPOINT", "https://example.monitor.azure.com")
    monkeypatch.setenv("LOGS_DCR_RULE_ID", "rule-1")
    monkeypatch.setenv("LOGS_DCR_STREAM_NAME", "stream-1")
    with (
        patch("govagent.telemetry.exporters.azure.DefaultAzureCredential", return_value=cred),
        patch("govagent.telemetry.exporters.azure.LogsIngestionClient", return_value=logs) as ctor,
    ):
        exporter = AzureMonitorExporter()
    ctor.assert_called_once()
    assert await exporter.export({"status": "success"}) is True
    logs.upload.assert_called_once_with(rule_id="rule-1", stream_name="stream-1", logs=[{"status": "success"}])

    logs.upload.side_effect = RuntimeError("denied")
    assert await exporter.export({"status": "error"}) is False


@pytest.mark.asyncio
async def test_jsonl_and_mock_exporters(tmp_path, capsys):
    path = tmp_path / "audit.jsonl"
    exporter = JsonlFileExporter(path=str(path))
    assert await exporter.export({"trace_id": "abc", "status": "success"}) is True
    written = path.read_text(encoding="utf-8").strip()
    assert "abc" in written

    mock = MockSOCExporter()
    assert await mock.export({"trace_id": "xyz"}) is True
    assert "xyz" in capsys.readouterr().out


def test_pricing_engine_known_and_default_models():
    engine = PricingEngine(markup_percent=10)
    gpt = engine.calculate_cost("gpt-4o", 1000)
    default = engine.calculate_cost("unknown-model", 1000)
    assert gpt > 0
    assert default > gpt
    cheap = PricingEngine(markup_percent=0).calculate_cost("gpt-3.5-turbo", 0)
    assert cheap == 0.0
