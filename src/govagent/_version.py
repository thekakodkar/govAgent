"""Single source of version: the installed package metadata, falling back to pyproject."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("govagent")
except PackageNotFoundError:  # pragma: no cover - unpackaged source tree
    __version__ = "3.5.1"

