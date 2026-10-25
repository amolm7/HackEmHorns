from uuid import UUID
from fastapi import APIRouter
from .common import Context, IdempotentContext
from .schemas import ProposalConfirm, AgentPatch, QuickCreate, AgentCapabilities

router = APIRouter(prefix="/api", tags=["Recruiter & workforce"])


@router.get("/recruiter/proposals")
def proposals(ctx: Context) -> list[dict]:
    return ctx.dispatch()


@router.post("/recruiter/proposals/{proposal_id}/confirm")
def confirm_proposal(
    proposal_id: UUID, body: ProposalConfirm, ctx: IdempotentContext
) -> dict:
    return ctx.dispatch(body)


@router.get("/agents")
def agents(
    ctx: Context, department_id: str | None = None, manager_id: str | None = None, include_archived: bool = False
) -> list[dict]:
    return ctx.dispatch()


@router.post("/agents/quick-create")
def quick_create(body: QuickCreate, ctx: IdempotentContext) -> dict:
    return ctx.dispatch(body)


@router.post("/agents/{agent_id}/capabilities")
def add_capabilities(agent_id: UUID, body: AgentCapabilities, ctx: IdempotentContext) -> dict:
    return ctx.dispatch(body)


@router.delete("/agents/{agent_id}")
def archive_agent(agent_id: UUID, ctx: Context) -> dict:
    return ctx.dispatch()


@router.get("/agents/{agent_id}")
def agent(agent_id: UUID, ctx: Context) -> dict:
    return ctx.dispatch()


@router.patch("/agents/{agent_id}")
def patch_agent(agent_id: UUID, body: AgentPatch, ctx: Context) -> dict:
    return ctx.dispatch(body)


@router.get("/agents/{agent_id}/versions")
def agent_versions(agent_id: UUID, ctx: Context) -> list[dict]:
    return ctx.dispatch()
