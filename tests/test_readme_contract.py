"""Documentation stays aligned with the public API."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_does_not_advertise_removed_apis():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "LOCAL_PREFERRED" not in readme
    assert "en_core_web_sm" not in readme
    assert "agent.run(" not in readme
    assert "policy_path=" not in readme.split("ExecutiveAgent(")[1].split("```")[0]


def test_index_has_no_merge_markers_or_fictional_imports():
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert "<<<<<<<" not in page
    # Allow MetaGovernor (the real class) but reject a standalone fictional Governor symbol.
    assert "GuardrailBoundary" not in page
    assert not re.search(r"(?<![A-Za-z])Governor(?![A-Za-z])", page)
    assert "from govagent import ExecutiveAgent, tool" in page or "ExecutiveAgent, tool" in page
