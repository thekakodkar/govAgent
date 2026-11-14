# src/govagent/governance/evidence.py

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from govagent._version import __version__


class Article9RiskMitigation(BaseModel):
    total_interceptions: int = 0
    privacy_redactions: int = 0
    semantic_intent_blocks: int = 0
    supply_chain_cve_rejections: int = 0


class Article12TraceRecord(BaseModel):
    trace_id: str
    parent_trace_id: str | None = None
    timestamp: str
    model: str
    cost_usd: float
    tool_manifest_hashes: list[str] = Field(default_factory=list)
    state_verdict: str


class SignerRecord(BaseModel):
    user_id: str
    role: str
    weight: float


class Article14OversightRecord(BaseModel):
    trace_id: str
    escalation_reason: str
    signers: list[SignerRecord] = Field(default_factory=list)
    total_quorum_score: float
    required_quorum: float
    consensus_verdict: str
    finalized_at: str


class ComplianceDossier(BaseModel):
    framework_version: str = Field(default_factory=lambda: __version__)
    export_id: str
    generated_at: str
    system_anchor: str
    eu_ai_act_article_9: Article9RiskMitigation
    eu_ai_act_article_12: list[Article12TraceRecord]
    eu_ai_act_article_14: list[Article14OversightRecord]
    dossier_sha256: str | None = None

    def seal(self) -> str:
        """Computes an immutable cryptographic digest of the complete compliance dossier."""
        payload = self.model_dump_json(exclude={"dossier_sha256"}).encode("utf-8")
        self.dossier_sha256 = hashlib.sha256(payload).hexdigest()
        return self.dossier_sha256


class EvidencePackGenerator:
    """Aggregates forensic buffers into verified regulatory audit packs."""

    def __init__(self, buffer_path: str | None = None):
        if buffer_path:
            self.buffer_path = Path(buffer_path)
        else:
            # Dynamically resolve root-level logs/audit_buffer.jsonl
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            self.buffer_path = project_root / "logs" / "audit_buffer.jsonl"

    def _parse_signatures(self, raw_signatures: list[Any]) -> list[SignerRecord]:
        parsed = []
        for sig in raw_signatures:
            if isinstance(sig, str) and "|" in sig:
                parts = sig.split("|")
                if len(parts) == 3:
                    parsed.append(
                        SignerRecord(
                            user_id=parts[0],
                            role=parts[1],
                            weight=float(parts[2]),
                        )
                    )
            elif isinstance(sig, dict):
                parsed.append(SignerRecord(**sig))
        return parsed

    def generate(self, system_anchor: str = "govagent-enterprise-mesh") -> ComplianceDossier:
        records: list[dict[str, Any]] = []
        if self.buffer_path.exists():
            with open(self.buffer_path, encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        records.append(json.loads(line_str))

        art9 = Article9RiskMitigation()
        art12_records = []
        art14_records = []

        for item in records:
            verdict = item.get("status", "UNKNOWN")

            # Article 9 Metric Accumulation
            if verdict in ["BLOCKED", "VETOED"]:
                art9.total_interceptions += 1
                reason = str(item.get("block_reason", "")).upper()
                if "PII" in reason or "PRIVACY" in reason:
                    art9.privacy_redactions += 1
                elif "SEMANTIC" in reason:
                    art9.semantic_intent_blocks += 1
                elif "HARBOR" in reason or "CVE" in reason:
                    art9.supply_chain_cve_rejections += 1

            # Article 12 Lineage Extraction
            art12_records.append(
                Article12TraceRecord(
                    trace_id=item.get("trace_id", "UNKNOWN"),
                    parent_trace_id=item.get("parent_trace_id"),
                    timestamp=item.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    model=item.get("selected_model", "undefined"),
                    cost_usd=float(item.get("recursive_tco_usd", 0.0)),
                    tool_manifest_hashes=item.get("tool_hashes", []),
                    state_verdict=verdict,
                )
            )

            # Article 14 Quorum Audit
            judiciary = item.get("judiciary_record")
            if judiciary:
                raw_sigs = judiciary.get("signatures", [])
                art14_records.append(
                    Article14OversightRecord(
                        trace_id=item.get("trace_id", "UNKNOWN"),
                        escalation_reason=judiciary.get("reason", "Threshold breach"),
                        signers=self._parse_signatures(raw_sigs),
                        total_quorum_score=float(judiciary.get("accumulated_weight", 0.0)),
                        required_quorum=float(judiciary.get("required_weight", 0.0)),
                        consensus_verdict=judiciary.get("verdict", "PENDING"),
                        finalized_at=judiciary.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    )
                )

        dossier = ComplianceDossier(
            export_id=f"EXP-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
            generated_at=datetime.now(timezone.utc).isoformat(),
            system_anchor=system_anchor,
            eu_ai_act_article_9=art9,
            eu_ai_act_article_12=art12_records,
            eu_ai_act_article_14=art14_records,
        )
        dossier.seal()
        return dossier