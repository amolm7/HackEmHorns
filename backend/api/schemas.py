"""Strict HTTP input contracts; business authorization stays in platform services."""

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=100, pattern=r"\S")]
LongText = Annotated[str, Field(min_length=1, max_length=4000, pattern=r"\S")]
Mode = Literal["demo", "meta", "gemini"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class Empty(Input):
    pass


class DepartmentCreate(Input):
    name: Text


class CapabilityCreate(Input):
    name: Text
    description: Annotated[str, Field(min_length=1, max_length=1000)]
    source: Literal["bundle", "github"] = "bundle"
    department_id: Text | None = None
    tools: Annotated[
        list[
            Literal[
                "search_tickets",
                "search_docs",
                "create_draft",
                "create_slideshow",
                "create_document",
                "analyze_data",
                "read_url",
                "schedule_meeting",
                "draft_email",
                "create_task_list",
            ]
        ],
        Field(min_length=1, max_length=10),
    ] | None = None

    @model_validator(mode="after")
    def source_fields(self):
        if self.source == "github":
            if self.tools is not None or self.department_id is None:
                raise ValueError("GitHub tools need a department and use the prepared connector's actions")
        elif not self.tools:
            raise ValueError("Choose actions for an existing tool bundle")
        return self


class CapabilityValidate(Input):
    connection_id: Text
    department_id: Text


class ConnectionPatch(Input):
    active: bool


class PolicyPatch(Input):
    require_all_approvals: bool | None = None
    approval_scope: Literal["agent", "action"] | None = None

    @model_validator(mode="after")
    def something(self):
        if not self.model_fields_set:
            raise ValueError("Provide require_all_approvals or approval_scope")
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class ListingCreate(Input):
    kind: Literal["agent", "capability"]
    source_id: Text


class ListingInstall(Input):
    department_id: Text | None = None
    manager_id: Text | None = None


class ProposalConfirm(Input):
    revision: Annotated[int, Field(ge=1)]


class ProposalReject(Input):
    reason: Annotated[str, Field(max_length=300)] = ""


class Binding(Input):
    capability_id: Text
    connection_id: Text
    validation_id: Text


class AgentPatch(Input):
    expected_spec_version: Annotated[int, Field(ge=1)]
    name: Text | None = None
    job_description: LongText | None = None
    instructions: Annotated[str, Field(min_length=1, max_length=8000)] | None = None
    model_profile_id: Mode | None = None
    department_id: Text | None = None
    manager_id: Text | None = None
    bindings: Annotated[list[Binding], Field(max_length=10)] | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(
                    f"{name} cannot be null; omit fields you are not changing"
                )
        return self


class RunCreate(Input):
    task: LongText
    mode: Mode = "demo"
    max_steps: Annotated[int, Field(ge=1, le=20)] = 12
    follow_up_of: Text | None = None
    conversation_id: Text | None = None
    repository: Annotated[str, Field(min_length=1, max_length=300)] | None = None


class GitHubConnect(Input):
    repository: Annotated[str, Field(min_length=1, max_length=300)]
    department_id: Text


class ReviewDecision(Input):
    decision: Literal["approve", "reject", "request_revision"]
    comment: Annotated[str, Field(max_length=2000)] = ""

    @model_validator(mode="after")
    def feedback_required(self):
        if self.decision == "request_revision" and not self.comment.strip():
            raise ValueError("Revision feedback is required")
        return self


class LevelChange(Input):
    level: Literal["intern", "associate"]
    reason: Annotated[str, Field(min_length=1, max_length=2000)]


class TaskOutcome(Input):
    success: bool
    comment: Annotated[str, Field(min_length=1, max_length=2000)]


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorInfo


class QuickCreate(Input):
    capability_ids: Annotated[list[Text], Field(min_length=1, max_length=10)] | None = None
    description: LongText | None = None
    name: Text | None = None
    model_profile_id: Mode = "demo"
    department_id: Text | None = None
    manager_id: Text | None = None

    @model_validator(mode="after")
    def needs_job(self):
        if not self.capability_ids and not self.description:
            raise ValueError("Choose capabilities or describe the job")
        return self


class AgentCapabilities(Input):
    expected_spec_version: Annotated[int, Field(ge=1)]
    capability_ids: Annotated[list[Text], Field(min_length=1, max_length=10)]
