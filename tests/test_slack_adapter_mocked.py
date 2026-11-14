from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from govagent.hitl.manager import ApprovalRequest
from govagent.hitl.slack_adapter import SlackJudiciaryAdapter


def _adapter() -> SlackJudiciaryAdapter:
    adapter = SlackJudiciaryAdapter(bot_token="xoxb-test", app_token="xapp-test", channel_id="C123")
    adapter.client = MagicMock()
    adapter.client.chat_postMessage.return_value = {"ts": "111.222"}
    adapter.socket_client = MagicMock()
    return adapter


def _request(**kwargs) -> ApprovalRequest:
    data = {
        "request_id": "req-1",
        "agent_id": "agent",
        "reason": "High-value transfer",
        "context": {},
        "required_score": 2.0,
        "risk_tier": "TIER_2_MATERIAL",
    }
    data.update(kwargs)
    return ApprovalRequest(**data)


def _interactive(action_id: str, user_id: str = "U1", request_id: str = "req-1") -> SimpleNamespace:
    return SimpleNamespace(
        type="interactive",
        envelope_id="env-1",
        payload={
            "actions": [{"action_id": action_id, "value": request_id}],
            "user": {"id": user_id},
        },
    )


def test_start_and_stop_wire_socket_listener():
    adapter = _adapter()
    adapter.start()
    adapter.socket_client.socket_mode_request_listeners.append.assert_called()
    adapter.socket_client.connect.assert_called_once()
    adapter.stop()
    adapter.socket_client.disconnect.assert_called_once()


def test_generate_blocks_with_and_without_signatures():
    adapter = _adapter()
    empty = adapter._generate_blocks(_request())
    assert empty[0]["type"] == "header"
    assert "No corporate signatures compiled" in empty[3]["text"]["text"]

    signed = _request(approvers={"U9|Director|2.0"})
    blocks = adapter._generate_blocks(signed)
    assert "<@U9>" in blocks[3]["text"]["text"]
    assert "2.0 / 2.0" in blocks[2]["text"]["text"]


def test_handle_interaction_ignores_non_interactive():
    adapter = _adapter()
    adapter.handle_interaction(adapter.socket_client, SimpleNamespace(type="event"))
    adapter.socket_client.send_socket_mode_response.assert_not_called()


@pytest.mark.asyncio
async def test_notify_and_quorum_approval():
    adapter = _adapter()
    request = _request()
    task = asyncio.create_task(adapter.notify(request))
    await asyncio.sleep(0)
    assert request.context["message_ts"] == "111.222"
    adapter.handle_interaction(adapter.socket_client, _interactive("approve_Lead", "U1"))
    await asyncio.sleep(0)
    assert not task.done()
    adapter.client.chat_update.assert_called()
    # Same user signing again must not double-count.
    adapter.handle_interaction(adapter.socket_client, _interactive("approve_Lead", "U1"))
    await asyncio.sleep(0)
    assert not task.done()
    adapter.handle_interaction(adapter.socket_client, _interactive("approve_Director", "U2"))
    result = await asyncio.wait_for(task, timeout=1)
    assert {row["voter_id"] for row in result} == {"U1", "U2"}
    assert all(row["decision"] == "APPROVED" for row in result)
    assert "req-1" not in adapter.pending_requests


@pytest.mark.asyncio
async def test_notify_veto_closes_future():
    adapter = _adapter()
    request = _request()
    task = asyncio.create_task(adapter.notify(request))
    await asyncio.sleep(0)
    adapter.handle_interaction(adapter.socket_client, _interactive("reject", "U9"))
    result = await asyncio.wait_for(task, timeout=1)
    assert result == [{"voter_id": "U9", "voter_role": "Executive", "decision": "REJECTED"}]
