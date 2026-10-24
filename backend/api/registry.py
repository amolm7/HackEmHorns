from fastapi import APIRouter
from .common import Context, IdempotentContext
from .schemas import (
    DepartmentCreate,
    CapabilityCreate,
    CapabilityValidate,
    ConnectionPatch,
    PolicyPatch,
    ListingCreate,
    ListingInstall,
)

router = APIRouter(prefix="/api", tags=["Registry & marketplace"])


@router.get("/me", tags=["Identity"])
def me(ctx: Context) -> dict:
    return ctx.dispatch()


@router.get("/dev/users", tags=["Identity"])
def users(ctx: Context) -> list[dict]:
    return ctx.dispatch()


@router.get("/model-profiles")
def model_profiles(ctx: Context) -> list[dict]:
    return ctx.dispatch()


@router.get("/departments")
def departments(ctx: Context) -> list[dict]:
    return ctx.dispatch()


@router.post("/departments")
def create_department(body: DepartmentCreate, ctx: Context) -> dict:
    return ctx.dispatch(body)


@router.get("/capabilities")
def capabilities(ctx: Context) -> list[dict]:
    return ctx.dispatch()


@router.post("/capabilities")
def create_capability(body: CapabilityCreate, ctx: Context) -> dict:
    return ctx.dispatch(body)


@router.get("/capabilities/{capability_id}")
def capability(capability_id: str, ctx: Context) -> dict:
    return ctx.dispatch()


@router.post("/capabilities/{capability_id}/validate")
def validate_capability(
    capability_id: str, body: CapabilityValidate, ctx: Context
) -> dict:
    return ctx.dispatch(body)


@router.get("/connections")
def connections(ctx: Context) -> list[dict]:
    return ctx.dispatch()


@router.patch("/connections/{connection_id}")
def patch_connection(connection_id: str, body: ConnectionPatch, ctx: Context) -> dict:
    return ctx.dispatch(body)


@router.get("/policy")
def policy(ctx: Context) -> dict:
    return ctx.dispatch()


@router.patch("/policy")
def patch_policy(body: PolicyPatch, ctx: Context) -> dict:
    return ctx.dispatch(body)


@router.get("/marketplace")
def marketplace(ctx: Context) -> list[dict]:
    return ctx.dispatch()


@router.post("/marketplace")
def publish_listing(body: ListingCreate, ctx: Context) -> dict:
    return ctx.dispatch(body)


@router.post("/marketplace/{listing_id}/install")
def install_listing(
    listing_id: str, body: ListingInstall, ctx: IdempotentContext
) -> dict:
    return ctx.dispatch(body)
