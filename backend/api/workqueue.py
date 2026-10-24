from typing import Literal
from fastapi import APIRouter
from .common import Context
from .schemas import Input, Empty, LongText, Text

router = APIRouter(prefix='/api/work-queue', tags=['Support work queue'])

class WorkCreate(Input):
    workflow: Literal['launch', 'analysis', 'brief']
    title: Text
    department_id: Text = "support"
    task: LongText

class SampleBatch(Input):
    workflow: Literal['support', 'launch', 'analysis', 'brief'] = 'support'

class Assignment(Input):
    agent_id: Text
    mode: Literal['demo', 'meta', 'gemini'] = 'demo'

class Review(Input):
    success: bool
    comment: LongText

@router.get('')
def queue(ctx: Context) -> list[dict]:
    return ctx.dispatch()

@router.post('')
def create(body: WorkCreate, ctx: Context) -> dict:
    return ctx.dispatch(body)

@router.post('/sample-batch')
def sample_batch(body: SampleBatch, ctx: Context) -> list[dict]:
    return ctx.dispatch(body)

@router.post('/{item_id}/assign')
def assign(item_id: str, body: Assignment, ctx: Context) -> dict:
    return ctx.service.handle('POST', ctx.request.url.path, {**body.model_dump(), 'agent_id': str(body.agent_id)}, ctx.actor_id)

@router.post('/{item_id}/review')
def review(item_id: str, body: Review, ctx: Context) -> dict:
    return ctx.dispatch(body)
