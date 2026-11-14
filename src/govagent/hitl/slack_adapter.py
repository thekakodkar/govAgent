import asyncio
import logging
from typing import Any

from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web import WebClient

from .manager import ApprovalRequest

logger = logging.getLogger("govagent.hitl.slack_adapter")

class SlackJudiciaryAdapter:
    """
    Refactored Institutional Multi-Signature Adapter (v0.6.0).
    Manages user interface delivery and maps user inputs to structured voting vectors.
    """
    def __init__(self, bot_token: str | None = None, app_token: str | None = None, channel_id: str = ""):
        self.channel_id = channel_id
        self.client = WebClient(token=bot_token or "")
        self.pending_requests: dict[str, tuple[ApprovalRequest, asyncio.Future]] = {}
        self.socket_client = SocketModeClient(app_token=app_token or "", web_client=self.client)
        
        # Mirror weights purely for real-time local display calculations
        self.voter_weights = {
            "C-Suite": 3.0,
            "Director": 2.0,
            "Auditor": 1.5,
            "Lead": 1.0,
            "Clerk": 0.5
        }

    def start(self) -> None:
        """Establishes the persistent WebSocket connection thread."""
        logger.info("🏛️ Judiciary Layer: Initializing Real-time Socket Mode listener...")
        self.socket_client.socket_mode_request_listeners.append(self.handle_interaction)  # type: ignore[arg-type]
        self.socket_client.connect()

    def stop(self) -> None:
        """Gracefully tears down the network context socket to avoid resource leaks."""
        logger.info("🏛️ Judiciary Layer: Severing Socket Mode connection...")
        self.socket_client.disconnect()

    async def notify(self, request: ApprovalRequest) -> list[dict[str, Any]]:
        """
        Dispatches the ballot layout and pauses core thread execution 
        until the required score signature array is compiled.
        """
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending_requests[request.request_id] = (request, future)

        # Dispatch the corporate ballot interface
        blocks = self._generate_blocks(request)
        response = self.client.chat_postMessage(
            channel=self.channel_id, 
            blocks=blocks,
            text=f"⚖️ Federated Approval Required: {request.reason}"
        )

        # Store message timestamp to preserve threaded tracking updates
        request.context["message_ts"] = response["ts"]

        try:
            return await future
        finally:
            if request.request_id in self.pending_requests:
                del self.pending_requests[request.request_id]

    def _generate_blocks(self, request: ApprovalRequest) -> list[dict[str, Any]]:
        """Compiles standard Slack block layouts reflecting progressive weights."""
        approvers_display = []
        current_score = 0.0
        
        # Parse the signature set ("user_id|role|weight")
        for signature in request.approvers:
            uid, role, weight = signature.split("|")
            current_score += float(weight)
            approvers_display.append(f"<@{uid}> (*{role}*)")
            
        approvers_list = ", ".join(approvers_display) or "_No corporate signatures compiled_"
        
        return [
            {
                "type": "header", 
                "text": {"type": "plain_text", "text": f"🛡️ GovAgent Control Panel: {request.risk_tier}"}
            },
            {
                "type": "section", 
                "text": {
                    "type": "mrkdwn", 
                    "text": f"*Agent Identity:* `{request.agent_id}`\n*Reason for Intervention:* {request.reason}"
                }
            },
            {
                "type": "section", 
                "text": {
                    "type": "mrkdwn", 
                    "text": f"📊 *Consensus Progress:* *`{current_score:.1f} / {request.required_score:.1f}`* accumulated weight points."
                }
            },
            {
                "type": "section", 
                "text": {"type": "mrkdwn", "text": f"✒️ *Audit Log Signatures:* {approvers_list}"}
            },
            {"type": "divider"},
            {
                "type": "actions", 
                "elements": [
                    {
                        "type": "button", 
                        "text": {"type": "plain_text", "text": "Approve as Lead (1.0) ✅"}, 
                        "style": "primary", 
                        "action_id": "approve_Lead", 
                        "value": request.request_id
                    },
                    {
                        "type": "button", 
                        "text": {"type": "plain_text", "text": "Approve as Director (2.0) 🔥"}, 
                        "style": "primary", 
                        "action_id": "approve_Director", 
                        "value": request.request_id
                    },
                    {
                        "type": "button", 
                        "text": {"type": "plain_text", "text": "Veto Transaction ❌"}, 
                        "style": "danger", 
                        "action_id": "reject", 
                        "value": request.request_id
                    }
                ]
            }
        ]

    def handle_interaction(self, client: SocketModeClient, req: SocketModeRequest) -> None:
        """Processes interaction events across the distributed workspace board."""
        if req.type != "interactive":
            return
        
        payload = req.payload
        action = payload["actions"][0]["action_id"]
        request_id = payload["actions"][0]["value"]
        user_id = payload["user"]["id"]

        # Prevent Slack HTTP transport gateway timeouts
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

        if request_id in self.pending_requests:
            request, future = self.pending_requests[request_id]

            if action.startswith("approve_"):
                assigned_role = action.split("_")[1]
                weight = self.voter_weights.get(assigned_role, 1.0)
                
                # Check for single-user duplication
                already_signed = any(sig.startswith(f"{user_id}|") for sig in request.approvers)
                if not already_signed:
                    signature_key = f"{user_id}|{assigned_role}|{weight}"
                    request.approvers.add(signature_key)
                
                # Map active strings back to standard payload blocks
                compiled_responses = []
                total_accumulated_score = 0.0
                
                for sig in request.approvers:
                    uid, role, w = sig.split("|")
                    total_accumulated_score += float(w)
                    compiled_responses.append({"voter_id": uid, "voter_role": role, "decision": "APPROVED"})
                
                if total_accumulated_score >= request.required_score:
                    # Target quorum met: Release thread and return payload list
                    self._generate_conclusion_card(request, future, compiled_responses, f"✅ QUORUM MET: Authorized at a weight of {total_accumulated_score:.1f}/{request.required_score:.1f}.")
                else:
                    # Update Ballot UI to render modern incremental tallies
                    self.client.chat_update(
                        channel=self.channel_id,
                        ts=request.context["message_ts"],
                        blocks=self._generate_blocks(request),
                        text="Governance tally in progress..."
                    )

            elif action == "reject":
                # Sovereign Veto instantly terminates session tracking
                compiled_responses = [{"voter_id": user_id, "voter_role": "Executive", "decision": "REJECTED"}]
                self._generate_conclusion_card(request, future, compiled_responses, f"❌ VETOED: Action instantly terminated by authority <@{user_id}>.")

    def _generate_conclusion_card(self, request, future, result, status_msg):
        """Closes the synchronous future loop and pushes an un-clickable conclusion snippet."""
        loop = future.get_loop()
        loop.call_soon_threadsafe(future.set_result, result)

        # Overwrite dynamic elements into static auditable outputs
        self.client.chat_update(
            channel=self.channel_id,
            ts=request.context["message_ts"],
            blocks=[
                {
                    "type": "section", 
                    "text": {"type": "mrkdwn", "text": f"⚖️ *Final Federated Decision:* {status_msg}"}
                }
            ],
            text="Voting Concluded."
        )