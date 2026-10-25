import asyncio
import json
from starlette.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from ..contracts import Error, digest
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


@router.get("/agents/{agent_id}/runs")
def agent_runs(
    agent_id: UUID, ctx: Context,
    status: Literal["queued", "running", "awaiting_approval", "completed", "failed", "cancelled"] | None = None,
) -> list[dict]:
    return ctx.dispatch()


@router.post("/agents/{agent_id}/conversations")
def new_conversation(agent_id: UUID, body: Empty, ctx: IdempotentContext) -> dict:
    return ctx.dispatch(body)


@router.get("/agents/{agent_id}/conversations")
def agent_conversations(agent_id: UUID, ctx: Context) -> list[dict]:
    return ctx.dispatch()


@router.get("/agents/{agent_id}/activity")
def agent_activity(agent_id: UUID, ctx: Context) -> dict:
    return ctx.dispatch()


async def activity_events(service, actor_id, agent_id, request, auth=None):
    """Bounded, reconnectable state stream. Recheck identity and access on every tick.

    No database transaction is held while waiting or while sending to the client.
    Snapshots contain durable state; reconnects need no lossy in-memory event queue.
    """
    previous = None
    for tick in range(400):
        if await request.is_disconnected():
            return
        try:
            if auth is not None:
                await run_in_threadpool(auth.actor, request, actor_id)
            snapshot = await run_in_threadpool(service.handle, "GET", f"/api/agents/{agent_id}/activity", None, actor_id)
        except Error:
            yield 'event: access-lost\ndata: {}\n\n'
            return
        signature = digest(snapshot)
        if signature != previous:
            yield "event: snapshot\ndata: " + json.dumps(snapshot) + "\n\n"
            previous = signature
        elif tick % 20 == 0:
            yield ": keepalive\n\n"
        await asyncio.sleep(0.75)


@router.get("/agents/{agent_id}/events", response_class=StreamingResponse)
async def agent_events(agent_id: UUID, ctx: Context):
    # Reject forbidden/missing agents before sending the streaming response headers.
    await run_in_threadpool(ctx.service.handle, "GET", f"/api/agents/{agent_id}/activity", None, ctx.actor_id)
    return StreamingResponse(
        activity_events(ctx.service, ctx.actor_id, str(agent_id), ctx.request, ctx.request.app.state.auth),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
