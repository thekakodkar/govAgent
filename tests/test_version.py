from govagent import __version__
from govagent.governance import ComplianceDossier
from govagent._version import __version__ as module_version


def test_dunder_version_is_populated():
    assert __version__
    assert __version__ == module_version
    assert __version__.count(".") >= 2


def test_compliance_dossier_defaults_to_package_version():
    dossier = ComplianceDossier(
        export_id="exp-1",
        generated_at="2026-11-14T00:00:00Z",
        system_anchor="test",
        eu_ai_act_article_9=__import__(
            "govagent.governance.evidence", fromlist=["Article9RiskMitigation"]
        ).Article9RiskMitigation(),
        eu_ai_act_article_12=[],
        eu_ai_act_article_14=[],
    )
    assert dossier.framework_version == __version__
