from __future__ import annotations

import json
from pathlib import Path

from govagent.compliance import DISCLAIMER, control_catalog_json, control_ids, load_control_mapping
from govagent.governance.evidence import EvidencePackGenerator


def test_control_mapping_is_packaged_and_not_a_certification():
    mapping = load_control_mapping()
    assert "not a certification" in mapping["disclaimer"].lower()
    ids = control_ids()
    assert "EU-AI-ACT-ART-9" in ids
    assert "EU-AI-ACT-ART-12" in ids
    assert "EU-AI-ACT-ART-14" in ids
    assert "ISO-42001-A.6" in ids
    assert "NIST-AI-RMF-GOVERN" in ids
    catalog = json.loads(control_catalog_json())
    assert catalog["schema_version"] == "1.0"
    assert DISCLAIMER


def test_evidence_generate_empty_buffer(tmp_path: Path):
    missing = tmp_path / "nope.jsonl"
    dossier = EvidencePackGenerator(buffer_path=str(missing)).generate("anchor")
    assert dossier.eu_ai_act_article_9.total_interceptions == 0
    assert dossier.eu_ai_act_article_12 == []
    assert dossier.eu_ai_act_article_14 == []
    assert dossier.dossier_sha256
    assert "EU-AI-ACT-ART-9" in dossier.mapped_controls
    assert dossier.control_mapping_version == "1.0"
    assert dossier.control_mapping_disclaimer
    assert "not a certification" in dossier.control_mapping_disclaimer.lower()


def test_evidence_generate_classifies_records_and_signatures(tmp_path: Path):
    path = tmp_path / "buffer.jsonl"
    records = [
        {
            "trace_id": "t-pii",
            "parent_trace_id": None,
            "timestamp": "2026-11-14T10:00:00Z",
            "selected_model": "local",
            "recursive_tco_usd": 0.2,
            "tool_hashes": ["abc"],
            "status": "BLOCKED",
            "block_reason": "PII detected in prompt",
        },
        {
            "trace_id": "t-sem",
            "timestamp": "2026-11-14T10:01:00Z",
            "selected_model": "local",
            "recursive_tco_usd": 0.0,
            "status": "VETOED",
            "block_reason": "SEMANTIC alignment failure",
        },
        {
            "trace_id": "t-cve",
            "timestamp": "2026-11-14T10:02:00Z",
            "status": "BLOCKED",
            "block_reason": "Harbor CVE high",
            "recursive_tco_usd": "1.5",
        },
        {
            "trace_id": "t-ok",
            "timestamp": "2026-11-14T10:03:00Z",
            "status": "success",
            "recursive_tco_usd": 0.01,
            "judiciary_record": {
                "reason": "High-risk tool",
                "signatures": ["U1|Director|2.0", {"user_id": "U2", "role": "Lead", "weight": 1.0}],
                "accumulated_weight": 3.0,
                "required_weight": 2.5,
                "verdict": "APPROVED",
                "timestamp": "2026-11-14T10:03:05Z",
            },
        },
        "   ",
    ]
    with path.open("w", encoding="utf-8") as handle:
        for item in records:
            if isinstance(item, str):
                handle.write(item + "\n")
            else:
                handle.write(json.dumps(item) + "\n")

    dossier = EvidencePackGenerator(buffer_path=str(path)).generate()
    assert dossier.eu_ai_act_article_9.total_interceptions == 3
    assert dossier.eu_ai_act_article_9.privacy_redactions == 1
    assert dossier.eu_ai_act_article_9.semantic_intent_blocks == 1
    assert dossier.eu_ai_act_article_9.supply_chain_cve_rejections == 1
    assert len(dossier.eu_ai_act_article_12) == 4
    assert dossier.eu_ai_act_article_12[2].cost_usd == 1.5
    assert len(dossier.eu_ai_act_article_14) == 1
    oversight = dossier.eu_ai_act_article_14[0]
    assert oversight.consensus_verdict == "APPROVED"
    assert {signer.user_id for signer in oversight.signers} == {"U1", "U2"}
    digest = dossier.seal()
    assert digest == dossier.dossier_sha256
    assert "NIST-AI-RMF-MEASURE" in dossier.mapped_controls
