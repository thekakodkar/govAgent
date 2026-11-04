"""The public govagent archives must not contain the control plane."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED = ("platform/", "govagent_platform", "src/app/", "api/server.py")


def test_library_archives_exclude_platform_and_unexported_governance():
    poetry = shutil.which("poetry") or str(Path.home() / ".local" / "bin" / "poetry")
    out = ROOT / ".wheel-layout"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    subprocess.check_call([poetry, "build", "-o", str(out)], cwd=ROOT)
    archives = [path for path in out.iterdir() if path.suffix in {".whl", ".gz"}]
    assert archives, "poetry build produced no archives"
    try:
        for archive in archives:
            names = _members(archive)
            joined = "\n".join(names)
            for banned in BANNED:
                assert banned not in joined, f"{archive.name} contains {banned}"
            init_text = _governance_init(archive)
            assert "CFOAnalyticsEngine" not in init_text
            assert "EvidencePackGenerator" not in init_text
    finally:
        shutil.rmtree(out, ignore_errors=True)


def _members(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    with tarfile.open(path, "r:gz") as archive:
        return archive.getnames()


def _governance_init(path: Path) -> str:
    marker = "govagent/governance/__init__.py"
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            name = next(item for item in archive.namelist() if item.endswith(marker))
            return archive.read(name).decode("utf-8")
    with tarfile.open(path, "r:gz") as archive:
        member = next(item for item in archive.getmembers() if item.name.endswith(marker))
        extracted = archive.extractfile(member)
        assert extracted is not None
        return extracted.read().decode("utf-8")
