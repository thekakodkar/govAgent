"""Control-mapping helpers. These are not a certification."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

import yaml

DISCLAIMER = (
    "This mapping is not a certification, audit opinion, or declaration of conformity "
    "with the EU AI Act, ISO/IEC 42001, or the NIST AI RMF."
)


@lru_cache(maxsize=1)
def load_control_mapping() -> dict[str, Any]:
    """Load the packaged YAML control catalogue."""
    source = resources.files("govagent.compliance").joinpath("controls.yaml")
    with source.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    data.setdefault("disclaimer", DISCLAIMER)
    return data


def control_catalog_json() -> str:
    return json.dumps(load_control_mapping(), indent=2)


def control_ids() -> list[str]:
    return [str(item.get("id")) for item in load_control_mapping().get("frameworks", []) if item.get("id")]
