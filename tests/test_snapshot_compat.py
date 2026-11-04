"""3.0.2 ExecutionSnapshot constructors still validate. New fields stay optional."""

from govagent.registry.schemas import ExecutionSnapshot


def test_3_0_2_constructor_still_validates():
    snapshot = ExecutionSnapshot(
        trace_id="tr-1",
        status="success",
        output="ok",
        metrics={"total_tokens": 1},
    )
    assert snapshot.output == "ok"
    assert snapshot.cost_center == "CC-GENAI-DEFAULT"


def test_output_may_be_omitted():
    snapshot = ExecutionSnapshot(trace_id="tr-2", status="success")
    assert snapshot.output is None


def test_cost_center_is_not_required():
    snapshot = ExecutionSnapshot(trace_id="tr-3", status="blocked", output=None, metrics={})
    assert snapshot.trace_id == "tr-3"
