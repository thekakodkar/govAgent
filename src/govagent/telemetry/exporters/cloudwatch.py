import contextlib
import json
import time
from typing import Any

import boto3

from .base import BaseExporter


class CloudWatchExporter(BaseExporter):
    """Forensic Exporter for AWS CloudWatch Logs."""
    def __init__(self, log_group: str = "/aws/govagent/forensics", log_stream: str = "audit-trail"):
        self.client = boto3.client('logs')
        self.log_group = log_group
        self.log_stream = log_stream
        self._ensure_log_resources()

    def _ensure_log_resources(self):
        """Ensures Institutional Log Groups exist."""
        with contextlib.suppress(self.client.exceptions.ResourceAlreadyExistsException):
            self.client.create_log_group(logGroupName=self.log_group)

    async def export(self, snapshot_data: dict[str, Any]) -> bool:
        """Streams telemetry to AWS SOC."""
        try:
            self.client.put_log_events(
                logGroupName=self.log_group,
                logStreamName=self.log_stream,
                logEvents=[{
                    'timestamp': int(time.time() * 1000),
                    'message': json.dumps(snapshot_data)
                }]
            )
            return True
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ CloudWatch Export Failed: {e}")
            return False