from dataclasses import dataclass
from typing import Annotated, Any
from fastapi import Depends, Header, Request
from pydantic import BaseModel
from ..app import Application


@dataclass
class RequestContext:
    request: Request
    service: Application
    actor_id: str
    key: str | None

    def dispatch(self, payload: BaseModel | None = None) -> Any:
        # Preserve exact operation/path/body identity for the existing transactional replay logic.
        url = self.request.url.path
        if self.request.url.query:
            url += "?" + self.request.url.query
        data = payload.model_dump(exclude_unset=True) if payload is not None else None
        return self.service.handle(
            self.request.method, url, data, self.actor_id, self.key
        )


ActorHeader = Annotated[
    str,
    Header(
        alias="X-Dev-User",
        min_length=1,
        max_length=100,
        description="Local demo identity only; not production authentication.",
    ),
]
OptionalKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=200,
        description="Required for replay-protected mutations; reuse only for retrying an identical request.",
    ),
]
RequiredKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=200,
        description="Persist this key for retries. A different payload with the same key conflicts.",
    ),
]


def context(request: Request, actor_id: ActorHeader = "pavan", key: OptionalKey = None):
    return RequestContext(request, request.app.state.service, actor_id, key)


def idempotent_context(
    request: Request, key: RequiredKey, actor_id: ActorHeader = "pavan"
):
    return RequestContext(request, request.app.state.service, actor_id, key)


Context = Annotated[RequestContext, Depends(context)]
IdempotentContext = Annotated[RequestContext, Depends(idempotent_context)]
