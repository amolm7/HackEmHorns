# FastAPI HTTP API contract

Base URL: `http://localhost:8000/api`. Swagger UI: `/docs`. Machine-readable OpenAPI: `/openapi.json`. All operations have explicit FastAPI routes; request bodies use strict Pydantic models. Unknown body fields are rejected instead of silently ignored. Responses are JSON. All timestamps are UTC ISO strings. IDs are UUIDs except fixed seed IDs. POST/PATCH require `Content-Type: application/json` and an object body. Requests over 50 KB are rejected.

## Identity, errors and replay protection

`AUTH_MODE=password` uses a server-side session cookie. POST `/auth/login` with username/password, GET `/auth/session` for a CSRF token, and include `X-CSRF-Token` on authenticated mutations. POST `/auth/logout` revokes the session. `X-Dev-User` is ignored in this mode. In development mode only, `X-Dev-User: pavan` selects a local test identity (default `pavan`). Production requires password mode and a configured HTTPS origin. See [operations](OPERATIONS.md). A `roles` or `level` field in a request cannot grant authority.

Seed users: `amol` (admin/manager), `tarun` (manager), `shaun` (builder), `pavan` (manager/builder), `member`, `auditor`. The test-only other organization identity is disabled in the running app.

Error envelope:

```json
{"error":{"code":"permission_denied","message":"Only the assigned manager or an organization admin may do this.","details":{}}}
```

401 = sign-in required/expired, 429 = rate limited, 503 = not ready, 400 = invalid domain input, 403 = permission/access denied, 404 = absent/inaccessible resource, 409 = state/version/idempotency conflict, 413 = oversized body, 415 = content type, 422 = Pydantic validation failure or unsupported sandbox request, 502 = model/tool transport failure. Malformed JSON, invalid UUIDs/enums, extra fields, type coercion attempts, and missing required idempotency headers now return 422. Validation errors keep the error envelope and include field locations/messages without echoing input values. HTTP mutations return 200 with the resource; run execution continues asynchronously.

Required `Idempotency-Key` header on proposal confirmation, marketplace install, run submission, approval decisions, task outcome recording, and all work-queue POST operations. The key is scoped to actor, org, operation and path. Same key/body returns the original result; same key/different body returns 409. Use a new UUID for a new operation, retain it for retries. Stored replay results are snapshots, so GET the resource for its current state.

## Identity and configuration

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | FastAPI liveness check |
| GET | `/me` | Current actor and explicit development identity mode |
| GET | `/dev/users` | Same-company seeded users for local actor selection |
| GET | `/model-profiles` | `demo`, `meta`, `gemini`; enabled flags, never keys |
| GET | `/departments` | Actor-visible departments |
| POST | `/departments` | Admin; body `{ "name": "Operations" }` |
| GET | `/connections` | Authorized metadata; secret references removed |
| PATCH | `/connections/{id}` | Admin; `{ "active": false }`; revocation affects pending execution |
| GET | `/policy` | Current organization's approval policy and revision |
| PATCH | `/policy` | Admin; `{ "require_all_approvals": true }` and/or `{ "approval_scope": "agent" \| "action" }`; increments policy revision. `agent` (default): actions of an approved agent run without per-action review. `action`: Interns ask before every action and anything with outside effects waits. |

Sandbox connection `support-local` permits Support only. Creating a new department does not grant it tools or connections.

## Capability registry and validation

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/capabilities` | Company catalog and server-controlled risk/schema metadata |
| GET | `/capabilities/{id}` | Approved capability details |
| POST | `/capabilities` | Admin; register a curated recipe using supported sandbox tools |
| POST | `/capabilities/{id}/validate` | Admin/manager/builder; test the authorized local binding |

Seed capability IDs: `ticket-search`, `help-docs`, `reply-drafts`. Tool IDs: `search_tickets` (read), `search_docs` (read), `create_draft` (always approve). `create_draft` saves a local draft and never sends it.

Workspace capability IDs: `make-slideshow`, `write-document`, `analyze-data`, `research-web`, `schedule-meetings`, `draft-email`, `plan-tasks`. Tool IDs added with the skills release: `schedule_meeting` (`local_write`: title, start `YYYY-MM-DDTHH:MM`, optional `duration_minutes`, `attendees`, `location`, `agenda`; result includes an `ics` string and `sent: false`), `draft_email` (always approve; saved, never sent), `create_task_list` (`local_write`; lines `- task | owner | due`). `create_slideshow` accepts an optional `theme`. Each capability record includes a read-only `skill` playbook string.

Register example:

```json
{"name":"Support research bundle","description":"Reuse both read tools","tools":["search_tickets","search_docs"]}
```

No arbitrary endpoint/code registration. Risk is taken from the trusted implementation, not request fields.

Validation request:

```json
{"connection_id":"support-local","department_id":"support"}
```

Result includes `id`, capability/version, connection, department, `passed`, `checks`, `evidence`, timestamp, and exact test scope. The write recipe is validated by discovery and a read-only fixture; no write executes during setup. Passed validation is bound to the exact capability version/connection/department.

Binding object used throughout:

```json
{"capability_id":"ticket-search","connection_id":"support-local","validation_id":"<passed-validation-id>"}
```

## Recruiter and hiring

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/recruiter/conversations` | Admin/manager/builder; body `{}` |
| GET | `/recruiter/conversations/{id}` | Conversation owner reads messages |
| POST | `/recruiter/conversations/{id}/messages` | Owner submits a setup request or updates the current draft |
| GET | `/recruiter/proposals` | Proposals visible to creator, assigned manager, or admin |
| GET | `/recruiter/proposals/{id}` | Exact review-card revision, missing fields, validation references |
| POST | `/recruiter/proposals/{id}/confirm` | Assigned manager/admin confirms exact revision; idempotency required |

Message example:

```json
{
  "message":"Hire an agent to triage urgent tickets and draft replies.",
  "name":"Ticket Triage",
  "department_id":"support",
  "manager_id":"pavan",
  "mode":"demo",
  "model_profile_id":"demo",
  "connection_id":"support-local"
}
```

`mode` is `demo`, `meta`, or `gemini`; live modes need the relevant key. Demo requests can also explicitly supply `capability_ids`, `job_description`, and `instructions`. Missing department/manager creates an incomplete proposal and asks for those fields. The next message in the same conversation revises the draft; stale cards cannot confirm a newer draft. Draft setup does bounded read-only validation, not active agent execution.

To add capabilities to an existing agent, include `target_agent_id` and optional `capability_ids`. Only its assigned manager/admin can propose this change. Existing and new capabilities appear in a combined review card. Confirmation creates a new spec version and resets autonomy to Intern.

Confirmation body: `{ "revision": 1 }`. The HTTP schema rejects an extra level field; new hires start Intern. Builder-created proposals require a manager/admin confirmation. A confirmed proposal returns the existing resource if confirmed again; idempotency keys provide atomic replay protection.

## Workforce and spec versions

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/agents` | Visible workforce; optional `department_id`, `manager_id` filters |
| GET | `/agents/{id}` | Agent spec and activation state |
| PATCH | `/agents/{id}` | Create a new spec revision; creator/manager/admin subject to role and department checks |
| GET | `/agents/{id}/versions` | Immutable spec snapshots |
| POST | `/agents/{id}/level` | Assigned manager/admin; manual Intern/Associate change with reason |
| GET | `/agents/{id}/performance` | Action reviews, run outcomes, and independent manager task assessments |

Editable fields: `name`, `job_description`, `instructions`, `model_profile_id`, `department_id`, `manager_id`, `bindings`. Include `expected_spec_version`. `level`, `status`, roles and org cannot be patched. Explicit nulls are rejected; omit fields you are not changing. Any spec edit resets autonomy to Intern. Builder edits remain `draft`; assigned manager/admin can activate using PATCH after reviewing the current spec. Marketplace installs begin `needs_connections`.

Activation example:

```json
{"expected_spec_version":1,"bindings":[{"capability_id":"ticket-search","connection_id":"support-local","validation_id":"<new-validation>"}]}
```

An installed agent must bind every required template capability. Connections/validation from its source never transfer. Every old run is pinned to its original spec version; an outstanding approval for an edited spec is stale and must not execute. Cancel the old run and submit a fresh one.

Level body: `{ "level": "associate", "reason": "Reviewed read behavior and source accuracy." }`. A level change does not alter tool/connection access. Demotion/current org policy is checked before the next action. Existing Inbox items still require an explicit decision.

## Runs and execution traces

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/agents/{id}/runs` | Start active agent; idempotency required |
| GET | `/runs` | Actor-visible runs; filter `agent_id`, `status` |
| GET | `/runs/{id}` | Current state/result/error and reported usage |
| GET | `/runs/{id}/steps` | Policy/approval/model/tool/error records |
| POST | `/runs/{id}/cancel` | Initiator, assigned manager, or admin; body `{}` |
| POST | `/runs/{id}/outcome` | Assigned manager/admin evaluates final task result; idempotency required |

Run request:

```json
{"task":"Triage the urgent login outage and draft a reply.","mode":"demo","max_steps":8}
```

Run state: `queued`, `running`, `awaiting_approval`, `completed`, `failed`, `cancelled`. `max_steps` is an integer 1–20 and limits executed tool calls. Live model turns are separately bounded. Poll GET for asynchronous progress. Only allowed tools can be requested; every action uses a server-resolved connection.

Cancellation blocks future actions; it cannot undo work already performed. An in-flight tool call returns a conflict until the local operation finishes. No public endpoint can directly resume an unapproved action.

Outcome request: `{ "success": true, "comment": "Checked the reply against the incident guide." }`. One immutable outcome per run. Completion means execution finished, not that a manager judged the task correct.

## Inbox and reviews

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/approvals` | Manager's assigned Inbox; admin/auditor can inspect org reviews; optional `status` |
| GET | `/approvals/{id}` | Immutable action snapshot, policy decision and prior tool evidence |
| POST | `/approvals/{id}/decision` | Assigned manager/admin decides; idempotency required |

Decision request:

```json
{"decision":"approve","comment":"Read scope and arguments checked."}
```

Other decisions: `reject`, `request_revision`. Revision requires nonempty feedback. Rejection prevents that action and fails the run. Revision rejects the old action and requires a new action/approval. Live mode feeds nonexecution plus feedback back to the model. Demo mode makes a labeled deterministic argument revision (read query replaced with feedback; draft body appends feedback).

Decision is transactional. Replays cannot dispatch another tool call. Approvals reference the exact action hash, agent/spec version and manager assignment. The runtime rechecks current policy and connection access before calling the approved tool.

## Company marketplace and metrics

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/marketplace` | Same-company listings and measured install counts |
| POST | `/marketplace` | Publish a portable capability or agent template |
| POST | `/marketplace/{id}/install` | Install portable recipe; idempotency required |
| GET | `/leaderboard` | Review statistics (minimum N=5) and publisher/original-creator/capability reuse totals |
| GET | `/audit` | Admin/auditor reads company audit events |

Publish body: `{ "kind": "agent", "source_id": "<agent-id>" }`, or `kind: capability` with a capability ID. Capability recipes include schemas/risks/test recipe; agent templates include job/instructions/model profile/capability versions. Neither includes secret references, connections, data, approvals, or trust. Publishing privileges require admin/manager/builder; publishing another agent also requires creator/manager/admin access.

Agent install body: `{ "department_id": "support", "manager_id": "pavan" }`. Returns `install` and `resource`; the agent is an Intern with no bindings. Capability install body `{}` returns an unbound recipe reference and measured install record; the actual capability is already in the same-company catalog and is bound/validated when attached to an agent. Global copies are not implemented.

Nutrition labels show actual validation counts and scope. Each listing retains its original creator separately from its publisher. Installs credit both the listing creator and reused capability creators. Publisher verification and security scanning are `null`; no badge is fabricated. The leaderboard does not calculate money/time savings or cross-company scores.

## UI backend improvements

All new mutation requests below use the configured session authentication (or `X-Dev-User` in development mode). Quick creation, capability additions, conversation creation, and runs require `Idempotency-Key`. Reuse a key only to retry the same payload.

| Method | Endpoint | Behavior |
| --- | --- | --- |
| POST | `/agents/quick-create` | `{capability_ids?, description?, name?, model_profile_id?, department_id?, manager_id?}`. Provide skills or a description. Returns `{status: "created", agent}` for an authorized manager/admin, otherwise `{status: "awaiting_confirmation", proposal}`. Uses the existing proposal validation and confirmation policy atomically. |
| POST | `/agents/{id}/capabilities` | `{capability_ids, expected_spec_version}`. Manager/admin only; validates connections and resets new authority to asks-first. Returns the versioned agent. |
| DELETE | `/agents/{id}` | Manager/admin soft archive; cancels unfinished runs and pending approvals. Returns 409 if a tool is executing. Retains audit/history. |
| GET | `/agents?include_archived=true` | Includes archived records visible under the same organization/department rules. Default excludes archives. |
| POST | `/agents/{id}/conversations` | `{}` creates a durable, actor-owned task conversation. |
| GET | `/agents/{id}/conversations` | Lists the caller's task conversations for the visible agent, in creation order. |
| GET | `/agents/{id}/runs` | Scoped run history, with optional validated `status` filter. |
| GET | `/agents/{id}/activity` | `{agent, runs, steps, approvals, conversations}` snapshot for a visible agent. Only the caller's authorized approvals and own conversations are included. |
| GET | `/agents/{id}/events` | Authenticated SSE. `snapshot` events carry the activity snapshot on changes; comments provide heartbeats. `access-lost` closes a stream when access changes. Reconnect after termination for the latest durable snapshot. |

`POST /agents/{id}/runs` additionally accepts `conversation_id`. It continues the latest completed turn in a live conversation, rejects parallel/stale/cross-user or cross-agent continuation, and requires the same model. A new conversation is needed after an unfinished task or to switch models. Legacy `follow_up_of` remains supported. Public runs include `conversation_id` and compatible `thread_id`.

Completed demo runs now include a persisted `result.answer`. New approval actions include `summary` in their immutable hash; old action records retain their existing hash format. Rename remains the existing versioned `PATCH /agents/{id}` operation, including its asks-first reset and pending-run invalidation behavior.

## Work queue and quality

`GET /work-queue` lists actor-visible jobs. `POST /work-queue` accepts `workflow` (`launch`, `analysis`, `brief`), `title`, `task`, optional `department_id`, and optional `acceptance`:

```json
{"workflow":"launch","title":"Campus launch","task":"Prepare the package.\nchannel,signups\nAmbassadors,180\nSocial,240","acceptance":{"slide_count":5,"required_sections":["Recommendation","Risks","Next steps"],"min_document_words":40}}
```

Analysis workflows require a CSV source in the brief. `POST /work-queue/sample-batch` loads labeled fictional input for a workflow. `POST /work-queue/{id}/assign` accepts `agent_id` and `mode`. `POST /work-queue/{id}/review` accepts `success` and `comment`; passing automated checks is necessary but not sufficient for manager acceptance. IDs here can also be stable seeded IDs, not just UUIDs.

Job results include `quality` (`passed`, individual checks, limits), artifacts, ownership, outcome and timestamps. A final run with missing/invalid deliverables gets `error_code=deliverable_validation` after at most one live repair attempt. Retryable provider errors preserve `retry_count` and `next_attempt_at`; exhaustion produces `error_code=retry_exhausted`. Rerun corrected/failed jobs through assignment; prior attempt IDs and deliverables remain available.

`GET /auth/config` is public and exposes only the authentication mode. `/health` and `/ready` are public liveness/readiness probes. Readiness is not an assertion of deployment security.

## Employee reporting

`GET /employees` requires manager/admin access. Returns department-scoped employees, their created agents and existing quality scores, run counts by executing employee, completed/failed counts, last task time, and provider-reported token totals. Task volume ranking does not imply quality or measured time savings. Prompts, credentials, and artifact contents are excluded.

For the local demo team, run `.venv/bin/python scripts/configure_team.py`: Pavan becomes a builder (employee), Shaun becomes manager/builder for both departments, and agents previously assigned to Pavan move to Shaun. Existing passwords are unchanged. Shaun needs his own provisioned account using `scripts/create_user.py`. This explicit setup does not alter default test fixtures.

## Agent controls (agent-level approval release)

- `POST /agents/{id}/runs` uses the agent's `model_profile_id`. Omit `mode`, or send the same value; any other value returns 409 `model_fixed`. Work-queue assignment follows the same rule.
- Agents record `creator_id` (who asked for it) and `approved_by` (who confirmed it).
- `DELETE /agents/{id}` may be called by the creator, the assigned manager or an admin.
- Default `approval_scope` comes from `APPROVAL_SCOPE` (default `agent`) when a policy has none.
