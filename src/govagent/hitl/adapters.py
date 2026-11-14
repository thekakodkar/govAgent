from typing import Protocol

from .manager import ApprovalRequest  # Relative import for the package structure


class HITLAdapter(Protocol):
    """Protocol for different notification channels (CLI, Slack, Teams)."""
    async def notify(self, request: ApprovalRequest) -> bool:
        ...

class CLIAdapter:
    """Standard Console Adapter for local development."""
    async def notify(self, request: ApprovalRequest) -> bool:
        print("\n--- 🛑 GOVAGENT INTERVENTION REQUIRED ---")
        print(f"ID: {request.request_id}")
        print(f"Reason: {request.reason}")
        
        # Note: input() is blocking; in production, you'd use an async-compatible 
        # library or wait for a webhook/socket event.
        user_input = input("\nDecision (y/n): ").strip().lower()
        return user_input.startswith('y')