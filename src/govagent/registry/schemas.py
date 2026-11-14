# src/govagent/registry/schemas.py

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FinancialTransactionIntent(BaseModel):
    """Strict schema for financial execution tools."""
    amount: float
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("amount", mode="before")
    def validate_numeric_amount(cls, v):
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError as exc:
                raise ValueError(f"Invalid monetary value: '{v}' is not a valid float.") from exc
        if not isinstance(v, (int, float)):
            raise TypeError("Amount must be an integer or float.")
        return float(v)


class ToolManifest(BaseModel):
    """Metadata and validation schema for registered tools."""
    name: str
    description: str
    risk_level: str = "LOW"
    cost_usd: float = 0.0
    requires_approval: bool = False
    param_schema: type[BaseModel] | None = None
    oci_repository: str | None = None
    artifact_digest: str | None = None


class ExecutionSnapshot(BaseModel):
    """Certified Forensic Snapshot for Article 12 Compliance."""
    trace_id: str
    status: str
    output: Any = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    parent_trace_id: str | None = None

    timestamp: str | None = None
    selected_model: str | None = "undefined"
    recursive_tco_usd: float = 0.0
    reasoning_steps: list[str] = Field(default_factory=list)
    guards_evaluated: list[str] = Field(default_factory=list)
    block_reason: str | None = None
    tool_hashes: list[str] = Field(default_factory=list)
    judiciary_record: dict[str, Any] | None = None

    # Phase 1 Accounting Tags
    cost_center: str | None = "CC-GENAI-DEFAULT"
    gl_account: str | None = "GL-640100-SOFTWARE"
    requested_exposure_usd: float | None = 0.0
    total_tokens: int | None = 0