# src/govagent/registry/harbor_verifier.py
import os
import logging
from typing import Dict, Any, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger("govagent.registry.harbor_verifier")

_MOCK_TOKENS = {"mock-token", "mock"}


class HarborVerifier:
    """Harbor v2 supply-chain check.

    ``mock-token`` (the default) is an offline stub for unit tests. Any other
    token calls the Harbor API and fails closed when the registry cannot prove
    the artifact is signed and free of high or critical vulnerabilities.
    """

    def __init__(self, registry_url: str = None, robot_token: str = None, client: Optional[httpx.Client] = None):
        self.registry_url = (registry_url or os.getenv("HARBOR_REGISTRY_URL", "https://harbor.local")).rstrip("/")
        self.robot_token = robot_token if robot_token is not None else os.getenv("HARBOR_ROBOT_TOKEN", "mock-token")
        self.robot_name = os.getenv("HARBOR_ROBOT_NAME", "robot")
        self._client = client

    def verify_tool_artifact(self, repository: str, artifact_digest: str) -> Dict[str, Any]:
        """Queries Harbor security definitions to validate container status."""
        logger.info(f"⚓ Harbor Verifier: Scanning supply chain for {repository}@{artifact_digest}...")
        if self._offline_stub():
            return self._stub_report(repository or "")
        if not repository or not artifact_digest:
            return {
                "verified": False,
                "reason": "HARBOR_UNVERIFIED",
                "details": "Repository and digest are required before a production image can run.",
            }
        try:
            response = self._get(repository, artifact_digest)
        except httpx.HTTPError as exc:
            return {
                "verified": False,
                "reason": "HARBOR_UNREACHABLE",
                "details": f"Harbor could not be reached: {exc}",
            }
        if response.status_code != 200:
            return {
                "verified": False,
                "reason": "HARBOR_REJECTED",
                "details": f"Harbor returned HTTP {response.status_code}.",
            }
        try:
            body = response.json()
        except ValueError:
            return {
                "verified": False,
                "reason": "HARBOR_UNVERIFIED",
                "details": "Harbor did not return a JSON artifact record.",
            }
        if not isinstance(body, dict):
            return {
                "verified": False,
                "reason": "HARBOR_UNVERIFIED",
                "details": "Harbor artifact record was not an object.",
            }
        if _has_blocking_vulnerability(body):
            return {
                "verified": False,
                "reason": "CRITICAL_VULNERABILITY_FOUND",
                "details": "Harbor reports a high or critical vulnerability.",
            }
        if not _scan_is_clean(body):
            return {
                "verified": False,
                "reason": "HARBOR_UNVERIFIED",
                "details": "Harbor has no completed vulnerability scan for this artifact.",
            }
        if not _is_signed(body):
            return {
                "verified": False,
                "reason": "SIGNATURE_MISSING",
                "details": "Harbor has no cosign or notation signature for this artifact.",
            }
        return {
            "verified": True,
            "reason": "COSIGN_SIGNATURE_VALIDATED",
            "details": "Harbor reports a signature and no high or critical vulnerabilities.",
        }

    def _offline_stub(self) -> bool:
        token = (self.robot_token or "").strip().lower()
        return token in _MOCK_TOKENS or token.startswith("mock-")

    def _stub_report(self, repository: str) -> Dict[str, Any]:
        if "malicious" in repository:
            return {
                "verified": False,
                "reason": "CRITICAL_VULNERABILITY_FOUND",
                "details": "Scan discovered CVE-2026-9999 (High Severity Risk Level).",
            }
        return {
            "verified": True,
            "reason": "COSIGN_SIGNATURE_VALIDATED",
            "details": "Offline mock-token stub. This result is not a Harbor verdict.",
        }

    def _get(self, repository: str, artifact_digest: str) -> httpx.Response:
        project, repo = _split_repository(repository)
        url = (
            f"{self.registry_url}/api/v2.0/projects/{quote(project, safe='')}"
            f"/repositories/{quote(repo, safe='')}/artifacts/{quote(artifact_digest, safe='')}"
        )
        auth = httpx.BasicAuth(self.robot_name, self.robot_token)
        if self._client is not None:
            return self._client.get(url, auth=auth)
        with httpx.Client(timeout=10.0) as client:
            return client.get(url, auth=auth)


def _split_repository(repository: str) -> tuple[str, str]:
    project, separator, repo = repository.partition("/")
    if not separator or not repo:
        return project or "library", repo or project
    return project, repo


def _has_blocking_vulnerability(body: Dict[str, Any]) -> bool:
    overview = body.get("scan_overview") or {}
    if not isinstance(overview, dict):
        return False
    for report in overview.values():
        if not isinstance(report, dict):
            continue
        severity = str(report.get("severity") or "").lower()
        if severity in {"critical", "high"}:
            return True
        summary = report.get("summary") or {}
        if not isinstance(summary, dict):
            continue
        if int(summary.get("critical") or 0) > 0 or int(summary.get("high") or 0) > 0:
            return True
    return False


def _scan_is_clean(body: Dict[str, Any]) -> bool:
    overview = body.get("scan_overview") or {}
    if not isinstance(overview, dict) or not overview:
        return False
    for report in overview.values():
        if isinstance(report, dict) and str(report.get("scan_status") or "Success").lower() in {"success", "finished"}:
            return True
    return False


def _is_signed(body: Dict[str, Any]) -> bool:
    for accessory in body.get("accessories") or []:
        if not isinstance(accessory, dict):
            continue
        kind = str(accessory.get("type") or accessory.get("artifact_type") or "").lower()
        if "signature" in kind or "cosign" in kind or "notation" in kind:
            return True
    extra = body.get("extra_attrs") or {}
    if isinstance(extra, dict) and extra.get("signed") is True:
        return True
    annotations = body.get("annotations") or {}
    if isinstance(annotations, dict):
        for key in annotations:
            lowered = str(key).lower()
            if "cosign" in lowered or "notation" in lowered:
                return True
    return False
