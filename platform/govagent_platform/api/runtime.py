"""Tenant runtime routes. The tenant id comes from the session, not the body."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from govagent_platform.authz.permissions import (
    TENANT_AGENTS_WRITE,
    TENANT_AUDIT_READ,
    TENANT_HITL_CONFIGURE,
    TENANT_HITL_VOTE,
    TENANT_RUNTIME_EVALUATE,
    TENANT_TOOLS_WRITE,
)
from govagent_platform.security.context import Actor
from govagent_platform.security.dependencies import get_db, require
from govagent_platform.services.agents import agent_payload, create_agent, list_agents
from govagent_platform.services.approvals import approval_payload, assign_hitl_role, cast_vote
from govagent_platform.services.errors import ServiceError
from govagent_platform.services.runtime import evaluate_agent, execution_payload
from govagent_platform.services.tools import create_tool, list_tools, tool_payload

router = APIRouter(prefix="/tenant/v1", tags=["tenant-runtime"])


class AgentBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    persona: str = Field(min_length=1, max_length=200)
    policy_id: UUID


class ToolBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    risk_level: str = "low"
    requires_approval: bool = False
    param_schema: dict | None = None
    oci_repository: str | None = None
    artifact_digest: str | None = None


class EvaluateBody(BaseModel):
    task: str = Field(min_length=1)


class VoteBody(BaseModel):
    decision: str


class HitlAssignmentBody(BaseModel):
    hitl_role: str


def _http(exc: ServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/agents", status_code=201)
def post_agent(
    body: AgentBody,
    actor: Actor = Depends(require(TENANT_AGENTS_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        row = create_agent(session, actor, name=body.name, persona=body.persona, policy_id=body.policy_id)
    except ServiceError as exc:
        raise _http(exc) from exc
    return agent_payload(row)


@router.get("/agents")
def get_agents(
    actor: Actor = Depends(require(TENANT_AGENTS_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        rows = list_agents(session, actor)
    except ServiceError as exc:
        raise _http(exc) from exc
    return [agent_payload(row) for row in rows]


@router.post("/tools", status_code=201)
def post_tool(
    body: ToolBody,
    actor: Actor = Depends(require(TENANT_TOOLS_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        row = create_tool(
            session,
            actor,
            name=body.name,
            description=body.description,
            risk_level=body.risk_level,
            requires_approval=body.requires_approval,
            param_schema=body.param_schema,
            oci_repository=body.oci_repository,
            artifact_digest=body.artifact_digest,
        )
    except ServiceError as exc:
        raise _http(exc) from exc
    return tool_payload(row)


@router.get("/tools")
def get_tools(
    actor: Actor = Depends(require(TENANT_TOOLS_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        rows = list_tools(session, actor)
    except ServiceError as exc:
        raise _http(exc) from exc
    return [tool_payload(row) for row in rows]


@router.post("/agents/{agent_id}/evaluate")
async def post_evaluate(
    agent_id: UUID,
    body: EvaluateBody,
    actor: Actor = Depends(require(TENANT_RUNTIME_EVALUATE)),
    session: Session = Depends(get_db),
):
    try:
        return await evaluate_agent(session, actor, agent_id, body.task)
    except ServiceError as exc:
        raise _http(exc) from exc


@router.get("/approvals/{request_id}")
def get_approval(
    request_id: UUID,
    actor: Actor = Depends(require(TENANT_RUNTIME_EVALUATE)),
    session: Session = Depends(get_db),
):
    try:
        return approval_payload(session, actor, request_id)
    except ServiceError as exc:
        raise _http(exc) from exc


@router.post("/approvals/{request_id}/votes")
async def post_vote(
    request_id: UUID,
    body: VoteBody,
    actor: Actor = Depends(require(TENANT_HITL_VOTE)),
    session: Session = Depends(get_db),
):
    try:
        request = await cast_vote(session, actor, request_id, body.decision)
    except ServiceError as exc:
        raise _http(exc) from exc
    return approval_payload(session, actor, request.id)


@router.put("/hitl-assignments/{identity_id}")
def put_assignment(
    identity_id: UUID,
    body: HitlAssignmentBody,
    actor: Actor = Depends(require(TENANT_HITL_CONFIGURE)),
    session: Session = Depends(get_db),
):
    try:
        row = assign_hitl_role(session, actor, identity_id, body.hitl_role)
    except ServiceError as exc:
        raise _http(exc) from exc
    return {"identity_id": str(row.identity_id), "hitl_role": row.hitl_role}


@router.get("/executions/{trace_id}")
def get_execution(
    trace_id: str,
    actor: Actor = Depends(require(TENANT_AUDIT_READ)),
    session: Session = Depends(get_db),
):
    try:
        return execution_payload(session, actor, trace_id)
    except ServiceError as exc:
        raise _http(exc) from exc
