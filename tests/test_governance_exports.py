import govagent.governance as governance
from govagent.governance import CFOAnalyticsEngine, ComplianceDossier, EvidencePackGenerator, MetaGovernor


def test_governance_package_exports_the_engines():
    assert governance.__all__ == [
        "MetaGovernor",
        "CFOAnalyticsEngine",
        "ComplianceDossier",
        "EvidencePackGenerator",
    ]
    assert governance.CFOAnalyticsEngine is CFOAnalyticsEngine
    assert governance.EvidencePackGenerator is EvidencePackGenerator
    assert governance.ComplianceDossier is ComplianceDossier
    assert governance.MetaGovernor is MetaGovernor
