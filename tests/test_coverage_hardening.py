from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from govagent.governance.cfo_analytics import CFOAnalyticsEngine
from govagent.hitl.adapters import CLIAdapter
from govagent.hitl.manager import ApprovalRequest
from govagent.registry.harbor_verifier import HarborVerifier
from govagent.telemetry.otel import _NullSpan, end_execute_span, otel_enabled, start_execute_span


def test_cli_adapter_approves_and_rejects(monkeypatch, capsys):
    request = ApprovalRequest(agent_id="a", reason="approve this", context={})
    adapter = CLIAdapter()
    monkeypatch.setattr("builtins.input", lambda _prompt="": "Yes")

    import asyncio

    assert asyncio.run(adapter.notify(request)) is True
    out = capsys.readouterr().out
    assert "GOVAGENT INTERVENTION REQUIRED" in out
    assert request.request_id in out

    monkeypatch.setattr("builtins.input", lambda _prompt="": "n")
    assert asyncio.run(adapter.notify(request)) is False


def test_otel_disabled_and_null_span(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    assert otel_enabled() is False
    span = start_execute_span(agent_id="director")
    assert isinstance(span, _NullSpan)
    span.set_attribute("k", "v")
    span.end()
    end_execute_span(span, status="success")
    end_execute_span(None, status="success")


def test_otel_span_attributes_and_failure_paths(monkeypatch):
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_SDK_DISABLED", "0")
    assert otel_enabled() is True

    class FakeSpan:
        def __init__(self):
            self.attrs: dict = {}
            self.ended = False

        def set_attribute(self, key, value):
            self.attrs[key] = value

        def end(self):
            self.ended = True

    class FakeTracer:
        def start_span(self, name):
            self.name = name
            self.span = FakeSpan()
            return self.span

    tracer = FakeTracer()
    with patch("govagent.telemetry.otel._tracer", return_value=tracer):
        span = start_execute_span(agent_id="director", model_name="gpt-4o", trace_id="tr-1")
    assert tracer.name == "gen_ai.invoke_agent"
    assert span.attrs["gen_ai.agent.name"] == "director"
    assert span.attrs["gen_ai.request.model"] == "gpt-4o"
    assert span.attrs["govagent.trace_id"] == "tr-1"
    end_execute_span(span, status="success", tokens=9, cost_usd=0.02, model_name="gpt-4o")
    assert span.ended is True
    assert span.attrs["gen_ai.usage.total_tokens"] == 9
    assert span.attrs["gen_ai.response.model"] == "gpt-4o"

    class BoomSpan:
        def set_attribute(self, *args, **kwargs):
            raise RuntimeError("exporter down")

        def end(self):
            return None

    end_execute_span(BoomSpan(), status="error")


def test_otel_uses_installed_api_tracer(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "0")
    span = start_execute_span(agent_id="director", model_name="m", trace_id="t")
    assert not isinstance(span, _NullSpan)
    end_execute_span(span, status="success", tokens=1, cost_usd=0.0, model_name="m")


def test_otel_tracer_import_error(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "no")
    import builtins

    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            raise ImportError("missing otel")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_import):
        span = start_execute_span(agent_id="director")
    assert isinstance(span, _NullSpan)


def test_cfo_analytics_aliases_blocked_spend_and_burn():
    engine = CFOAnalyticsEngine()
    empty = engine.analyze()
    assert empty.total_realized_spend_usd == 0.0
    assert empty.average_cost_per_work_unit == 0.0
    assert empty.burn_rate_anomaly_detected is False

    ok = SimpleNamespace(cost_center="CC-A", gl_account="GL-1", recursive_tco_usd=0.2, total_tokens=10, status="success")
    engine.record_snapshot(ok)
    blocked = SimpleNamespace(
        cost_center="CC-A",
        recursive_tco_usd=0.0,
        total_tokens=0,
        status="BLOCKED",
        requested_exposure_usd=12.5,
    )
    engine.record_transaction(blocked)
    hot = SimpleNamespace(cost_center="CC-B", recursive_tco_usd=0.75, total_tokens=4, status="success")
    engine.record_execution(hot)
    pending = SimpleNamespace(status="PENDING", requested_exposure_usd=3.0, recursive_tco_usd=0)
    engine.record_execution(pending)

    report = engine.analyze()
    assert report.total_realized_spend_usd == pytest.approx(0.95)
    assert report.value_at_risk_prevented_usd == pytest.approx(15.5)
    assert report.burn_rate_anomaly_detected is True
    assert report.average_cost_per_work_unit > 0
    assert "CC-A" in report.allocations_by_center
    assert report.allocations_by_center["CC-A"].transaction_count == 2


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_harbor_requires_repository_and_digest():
    verifier = HarborVerifier(registry_url="https://harbor.example", robot_token="real-secret", client=_client(lambda r: httpx.Response(500)))
    report = verifier.verify_tool_artifact("", "")
    assert report["verified"] is False
    assert report["reason"] == "HARBOR_UNVERIFIED"


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (httpx.Response(200, text="not-json"), "HARBOR_UNVERIFIED"),
        (httpx.Response(200, json=["not-an-object"]), "HARBOR_UNVERIFIED"),
        (httpx.Response(200, json={"scan_overview": {"vuln": {"scan_status": "pending"}}}), "HARBOR_UNVERIFIED"),
        (httpx.Response(200, json={"scan_overview": {"vuln": {"scan_status": "Success", "severity": "low"}}}), "SIGNATURE_MISSING"),
        (
            httpx.Response(
                200,
                json={
                    "scan_overview": {"vuln": {"scan_status": "Success", "summary": {"critical": 0, "high": 2}}},
                    "accessories": [{"type": "signature.cosign"}],
                },
            ),
            "CRITICAL_VULNERABILITY_FOUND",
        ),
    ],
)
def test_harbor_fail_closed_payloads(payload, reason):
    verifier = HarborVerifier(
        registry_url="https://harbor.example",
        robot_token="real-secret",
        client=_client(lambda request: payload),
    )
    report = verifier.verify_tool_artifact("payments/api", "sha256:abc")
    assert report["verified"] is False
    assert report["reason"] == reason


def test_harbor_accepts_signed_via_attrs_and_annotations():
    def handler(request):
        if "attr" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "scan_overview": {"vuln": {"scan_status": "finished", "severity": "none"}},
                    "extra_attrs": {"signed": True},
                },
            )
        return httpx.Response(
            200,
            json={
                "scan_overview": "not-a-dict",
                "annotations": {"cosign.sigstore.dev/signature": "yes"},
            },
        )

    verifier = HarborVerifier(
        registry_url="https://harbor.example",
        robot_token="real-secret",
        client=_client(handler),
    )
    # scan_overview as non-dict means _has_blocking_vulnerability is False and _scan_is_clean is False
    unsigned_scan = HarborVerifier(
        registry_url="https://harbor.example",
        robot_token="real-secret",
        client=_client(
            lambda request: httpx.Response(
                200,
                json={
                    "scan_overview": {"vuln": {"scan_status": "Success"}},
                    "annotations": {"cosign.sigstore.dev/signature": "yes"},
                },
            )
        ),
    )
    assert unsigned_scan.verify_tool_artifact("payments/api", "sha256:abc")["verified"] is True
    assert verifier.verify_tool_artifact("payments/attr", "sha256:abc")["verified"] is True


def test_harbor_scan_overview_skips_non_dict_and_non_int_summary():
    verifier = HarborVerifier(
        registry_url="https://harbor.example",
        robot_token="real-secret",
        client=_client(
            lambda request: httpx.Response(
                200,
                json={
                    "scan_overview": {
                        "odd": "skip",
                        "vuln": {"scan_status": "Success", "summary": "nope"},
                    },
                    "accessories": ["skip", {"type": "notation"}],
                },
            )
        ),
    )
    assert verifier.verify_tool_artifact("library/tool", "sha256:abc")["verified"] is True


def test_harbor_split_and_non_dict_scan_overview():
    verifier = HarborVerifier(
        registry_url="https://harbor.example",
        robot_token="real-secret",
        client=_client(
            lambda request: httpx.Response(
                200,
                json={"scan_overview": "not-a-dict", "extra_attrs": {"signed": True}},
            )
        ),
    )
    report = verifier.verify_tool_artifact("payments/", "sha256:abc")
    assert report["verified"] is False
    assert report["reason"] == "HARBOR_UNVERIFIED"

    empty_scan = HarborVerifier(
        registry_url="https://harbor.example",
        robot_token="real-secret",
        client=_client(lambda request: httpx.Response(200, json={"scan_overview": {}, "extra_attrs": {"signed": True}})),
    )
    assert empty_scan.verify_tool_artifact("payments/api", "sha256:abc")["reason"] == "HARBOR_UNVERIFIED"


def test_harbor_mock_prefix_still_offline():
    report = HarborVerifier(robot_token="mock-ci").verify_tool_artifact("example/tool", "sha256:abc")
    assert "Offline mock-token stub" in report["details"]
