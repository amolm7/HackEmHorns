from typing import Literal
from fastapi import APIRouter
from .common import Context, IdempotentContext
from .schemas import Input, LongText, Text
from pydantic import Field
from typing import Annotated

router = APIRouter(prefix="/api/work-queue", tags=["Work queue"])


class Acceptance(Input):
    slide_count: Annotated[int, Field(ge=3, le=20)] | None = None
    required_sections: (
        Annotated[list[Text], Field(min_length=1, max_length=10)] | None
    ) = None
    min_document_words: Annotated[int, Field(ge=20, le=500)] | None = None


class WorkCreate(Input):
    workflow: Literal["launch", "analysis", "brief"]
    title: Text
    department_id: Text = "support"
    task: LongText
    acceptance: Acceptance | None = None


class SampleBatch(Input):
    workflow: Literal["support", "launch", "analysis", "brief"] = "support"


class Assignment(Input):
    agent_id: Text
    mode: Literal["demo", "meta", "gemini"] = "demo"


class Review(Input):
    success: bool
    comment: LongText


@router.get("")
def queue(ctx: Context) -> list[dict]:
    return ctx.dispatch()


@router.post("")
def create(body: WorkCreate, ctx: IdempotentContext) -> dict:
    return ctx.dispatch(body)


@router.post("/sample-batch")
def sample_batch(body: SampleBatch, ctx: IdempotentContext) -> list[dict]:
    return ctx.dispatch(body)


@router.post("/{item_id}/assign")
def assign(item_id: str, body: Assignment, ctx: IdempotentContext) -> dict:
    return ctx.dispatch(body)


@router.post("/{item_id}/review")
def review(item_id: str, body: Review, ctx: IdempotentContext) -> dict:
    return ctx.dispatch(body)
