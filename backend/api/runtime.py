from typing import Literal
from uuid import UUID
from fastapi import APIRouter
from .common import Context, IdempotentContext
from .schemas import RunCreate, Empty

router = APIRouter(prefix="/api", tags=["Execution & traces"])


@router.post("/agents/{agent_id}/runs")
def start_run(agent_id: UUID, body: RunCreate, ctx: IdempotentContext) -> dict:
    return ctx.dispatch(body)


@router.get("/runs")
def runs(
    ctx: Context,
    agent_id: UUID | None = None,
    status: (
        Literal[
            "queued", "running", "awaiting_approval", "completed", "failed", "cancelled"
        ]
        | None
    ) = None,
) -> list[dict]:
    return ctx.dispatch()


@router.get("/runs/{run_id}")
def run(run_id: UUID, ctx: Context) -> dict:
    return ctx.dispatch()


@router.get("/runs/{run_id}/steps")
def run_steps(run_id: UUID, ctx: Context) -> list[dict]:
    return ctx.dispatch()


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: UUID, body: Empty, ctx: Context) -> dict:
    return ctx.dispatch(body)
