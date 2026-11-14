from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field, computed_field


class LLMRequest(BaseModel):
    prompt: str
    temperature: float = 0.0
    max_tokens: int | None = None
    system_instruction: str | None = None
    tools: list[dict[str, Any]] | None = None


class LLMResponse(BaseModel):
    text: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    raw_usage: dict[str, int | float] = Field(default_factory=dict)
    model_name: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def selected_model(self) -> str:
        """Compatibility alias used by ExecutiveAgent metrics."""
        return self.model_name


class BaseLLMClient(ABC):
    """
    Sovereign LLM abstraction layer. Ensures GovAgent evaluates intent
    and handles local data redaction uniformly regardless of the provider.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Executes raw generation. Guards hook into this lifecycle out-of-band."""
