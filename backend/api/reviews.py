from typing import Literal
from uuid import UUID
from fastapi import APIRouter
from .common import Context, IdempotentContext
from .schemas import ReviewDecision, LevelChange, TaskOutcome

router = APIRouter(prefix="/api", tags=["Reviews & performance"])


@router.get("/approvals")
def approvals(
    ctx: Context,
    status: (
        Literal["pending", "approved", "rejected", "revision_requested", "cancelled"]
        | None
    ) = None,
) -> list[dict]:
    return ctx.dispatch()


@router.get("/approvals/{approval_id}")
def approval(approval_id: UUID, ctx: Context) -> dict:
    return ctx.dispatch()


@router.post("/approvals/{approval_id}/decision")
def decide_approval(
    approval_id: UUID, body: ReviewDecision, ctx: IdempotentContext
) -> dict:
    return ctx.dispatch(body)


@router.post("/agents/{agent_id}/level")
def change_level(agent_id: UUID, body: LevelChange, ctx: Context) -> dict:
    return ctx.dispatch(body)


@router.get("/agents/{agent_id}/performance")
def performance(agent_id: UUID, ctx: Context) -> dict:
    return ctx.dispatch()


@router.post("/runs/{run_id}/outcome")
def task_outcome(run_id: UUID, body: TaskOutcome, ctx: IdempotentContext) -> dict:
    return ctx.dispatch(body)


@router.get("/leaderboard")
def leaderboard(ctx: Context) -> dict:
    return ctx.dispatch()


@router.get("/audit")
def audit(ctx: Context) -> list[dict]:
    return ctx.dispatch()
