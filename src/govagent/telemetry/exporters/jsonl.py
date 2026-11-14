from __future__ import annotations

import json
import os
from typing import Any

from .base import BaseExporter


class JsonlFileExporter(BaseExporter):
    """Append-only JSONL audit sink used as the default Article 12 ledger."""

    def __init__(self, path: str = "logs/audit_trail.jsonl"):
        self.path = path
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    async def export(self, snapshot_data: dict[str, Any]) -> bool:
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot_data, default=str) + "\n")
        return True
