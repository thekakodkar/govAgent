import contextvars
from typing import Any

_current_agent = contextvars.ContextVar("current_agent", default=None)

def set_current_agent(agent: Any):
    """Enrolls the agent and returns a reset token."""
    return _current_agent.set(agent)

def get_current_agent() -> Any | None:
    """Retrieves the active agent for trace inheritance."""
    return _current_agent.get()

def reset_current_agent(token):
    """Cleanses the async thread context."""
    _current_agent.reset(token)