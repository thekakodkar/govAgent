import os

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from govagent_platform.telemetry import configure_provider
from tests.platform.runtime_support import activate_tenant_policy, make_agent, script_task


def test_evaluate_span_has_ids_and_not_the_task(client):
    exporter = InMemorySpanExporter()
    previous = os.environ.get("OTEL_SDK_DISABLED")
    os.environ["OTEL_SDK_DISABLED"] = "false"
    try:
        provider = TracerProvider()
    finally:
        if previous is None:
            os.environ.pop("OTEL_SDK_DISABLED", None)
        else:
            os.environ["OTEL_SDK_DISABLED"] = previous
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    configure_provider(provider)

    policy_id = activate_tenant_policy(client, daily=100)
    agent_id = make_agent(
        client,
        policy_id,
        "record_note",
        requires_approval=False,
        param_schema={"required": []},
        agent_name="span-agent",
    )
    task = script_task("record_note", tokens=10)
    response = client.post(f"/tenant/v1/agents/{agent_id}/evaluate", json={"task": task})
    assert response.status_code == 200, response.text
    spans = [span for span in exporter.get_finished_spans() if span.name == "tenant.evaluate"]
    assert spans
    attributes = spans[-1].attributes
    assert attributes["trace_id"] == response.json()["trace_id"]
    assert attributes["tenant_id"]
    assert attributes["govagent.status"] == "success"
    assert task not in attributes.values()
