import os
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.monitor.ingestion import LogsIngestionClient

from .base import BaseExporter


class AzureMonitorExporter(BaseExporter):
    """Forensic Exporter for Azure Log Analytics."""
    def __init__(self):
        # Configuration from Azure Environment Variables
        self.endpoint = os.environ.get("DATA_COLLECTION_ENDPOINT")
        self.rule_id = os.environ.get("LOGS_DCR_RULE_ID")
        self.stream_name = os.environ.get("LOGS_DCR_STREAM_NAME")
        
        self.credential = DefaultAzureCredential()
        self.client = LogsIngestionClient(endpoint=self.endpoint or "", credential=self.credential)

    async def export(self, snapshot_data: dict[str, Any]) -> bool:
        """Streams telemetry to Azure Monitor."""
        try:
            self.client.upload(
                rule_id=self.rule_id or "",
                stream_name=self.stream_name or "",
                logs=[snapshot_data]
            )
            return True
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Azure Monitor Export Failed: {e}")
            return False