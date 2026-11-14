# src/govagent/hitl/__init__.py

from .adapters import CLIAdapter, HITLAdapter
from .manager import ApprovalRequest, ApprovalStatus, HITLManager
from .slack_adapter import SlackJudiciaryAdapter

# This allows: from govagent.hitl import HITLManager
__all__ = [
    "ApprovalRequest",
    "ApprovalStatus",
    "CLIAdapter",
    "HITLAdapter",
    "HITLManager",
    "SlackJudiciaryAdapter"
]
