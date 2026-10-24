from uuid import UUID
from fastapi import APIRouter
from .common import Context, IdempotentContext
from .schemas import Empty, RecruiterMessage, ProposalConfirm, AgentPatch

router = APIRouter(prefix="/api", tags=["Recruiter & workforce"])


@router.post("/recruiter/conversations")
def start_conversation(body: Empty, ctx: Context) -> dict:
    return ctx.dispatch(body)


@router.get("/recruiter/conversations/{conversation_id}")
def conversation(conversation_id: UUID, ctx: Context) -> dict:
    return ctx.dispatch()


@router.post("/recruiter/conversations/{conversation_id}/messages")
def recruiter_message(
    conversation_id: UUID, body: RecruiterMessage, ctx: Context
) -> dict:
    return ctx.dispatch(body)


@router.get("/recruiter/proposals")
def proposals(ctx: Context) -> list[dict]:
    return ctx.dispatch()


@router.get("/recruiter/proposals/{proposal_id}")
def proposal(proposal_id: UUID, ctx: Context) -> dict:
    return ctx.dispatch()


@router.post("/recruiter/proposals/{proposal_id}/confirm")
def confirm_proposal(
    proposal_id: UUID, body: ProposalConfirm, ctx: IdempotentContext
) -> dict:
    return ctx.dispatch(body)


@router.get("/agents")
def agents(
    ctx: Context, department_id: str | None = None, manager_id: str | None = None
) -> list[dict]:
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
