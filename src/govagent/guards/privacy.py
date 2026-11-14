from __future__ import annotations

from typing import Any

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine

_DEFAULT_ENTITIES = ["PERSON", "LOCATION", "PHONE_NUMBER", "EMAIL_ADDRESS"]


class PrivacyGuard:
    """Article 9 Compliance: PII & Location Redaction."""

    def __init__(self, policy: Any):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        self.last_execution_had_pii = False

        address_regex = r"\d+\s+[A-Z][a-z]+\s+(St|Ave|Rd|Blvd|Street|Road|Lane)"
        address_pattern = Pattern(name="address_pattern", regex=address_regex, score=0.8)
        address_recognizer = PatternRecognizer(supported_entity="LOCATION", patterns=[address_pattern])
        self.analyzer.registry.add_recognizer(address_recognizer)

        entities = list(_DEFAULT_ENTITIES)
        oversight = getattr(policy, "oversight", None) or {}
        privacy_cfg = oversight.get("privacy") if isinstance(oversight, dict) else None
        if isinstance(privacy_cfg, dict):
            declared = privacy_cfg.get("target_entities")
            if isinstance(declared, list):
                for item in declared:
                    if item and str(item) not in entities:
                        entities.append(str(item))
        self.target_entities = entities

    def redact_task(self, text: str) -> str:
        results = self.analyzer.analyze(text=text, entities=self.target_entities, language="en")
        self.last_execution_had_pii = bool(results)
        return self.anonymizer.anonymize(text=text, analyzer_results=results).text  # type: ignore[arg-type]

    def anonymize(self, text: str) -> str:
        """Alias for ``redact_task`` used by the IBM Bob MCP proxy."""
        return self.redact_task(text)
