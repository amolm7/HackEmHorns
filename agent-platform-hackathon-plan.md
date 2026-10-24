# Hire an Agent — HackTX Platform Plan

> Describe the job. Hire the agent. Let it earn trust.

## 1. Concept

An enterprise agent platform that combines employee-style onboarding with a company marketplace of reusable capabilities. Users describe a job to a Recruiter helper. It proposes an agent with a department, manager, instructions, tools, and explicit permissions. A human reviews the job card and hires the agent as an Intern. The agent starts with supervised work and can be manually promoted as its manager reviews real results.

Teams publish reusable capability recipes and agent templates internally. Other teams install those recipes, bind their own authorized connections, and validate them. Reuse is visible through creator attribution and installation counts. Trust and credentials never transfer with a template.

**Why this product:** Teams should not rebuild the same capabilities or give new agents unrestricted autonomy. Hire from shared company expertise, then expand autonomy through reviewed work.

**Project reset:** This document replaces the previous Proof/document-research prototype and its plan. The earlier implementation has been removed from the repository. This is a design and implementation plan, not a statement that the features below already exist.

## 2. People and agent authority

People get roles controlling what they may change. Agents get permission rules controlling which actions may run without review. All decisions are enforced by the backend.

| Human role | Intended authority |
| --- | --- |
| Admin | Manage departments, approved capabilities, organization policies, and role assignments |
| Manager | Confirm hires, review assigned agents' work, promote or demote |
| Builder | Draft and edit agents; manager confirmation required before activation |
| Member | Use agents they are authorized to access |
| Auditor | Read permitted profiles, traces, and audit events |

The hackathon can use documented seeded identities for these checks. A browser-selected role is not production authentication.

| Agent level | MVP behavior / future direction |
| --- | --- |
| Intern | Every proposed tool action pauses for manager review |
| Associate | Approved read actions can run without review; explicitly allowed low-risk writes may be supported later |
| Senior | Roadmap: broader scoped autonomy with manager summaries |
| Lead | Roadmap: scoped delegation to other agents |

High-risk tools always require human review. A promotion never grants access to a new connection or tool on its own. Organization policy can impose stricter review at every level. For the demo, use reads and local drafts rather than destructive or financial actions.

## 3. Recruiter and review cards

The Recruiter is a conversational setup helper. It proposes; platform services authorize and commit.

### Hire an agent

Example: “I need an agent that reads support tickets, flags urgent ones, and drafts replies.”

1. Recruiter finds appropriate company capabilities and asks for missing department, manager, or task details.
2. It proposes a job card containing the job, instructions, capabilities, required connection permissions, model profile, manager, department, and Intern level.
3. Platform services validate the proposal against the approved catalog and the actor's permissions.
4. The authorized manager confirms the exact reviewed revision.
5. The backend saves an agent spec. Confirmation replay must return the same hire, not create a second agent.

### Add a capability

Example: “Let our engineering agents read GitHub issues.”

1. Search the company catalog first. Global discovery is a roadmap item.
2. Propose an approved capability, its tool schemas, and required permissions. Tool risk comes from the server-controlled catalog and organization policy, not the Recruiter.
3. Bind an authorized connection. Credentials never enter chat or an agent spec.
4. Execute a bounded validation test and show actual evidence.
5. An authorized human confirms the proposal; attach the approved version to the agent.

Capability creation from arbitrary API documentation and proactive training suggestions are roadmap items.

## 4. Company marketplace

**Agent templates:** job description, instructions, and capability/version references.

**Capability recipes:** tool/config schemas, permissions, input/output contracts, test definitions, and creator attribution.

Listings show a nutrition label: tools, risk classes, required data access, supported model profile where relevant, and actual validation evidence with its sample size/date. Installing never imports credentials, connection IDs, task data, approvals, or trust history. New agent installs start as Interns and require local connection checks.

Build internal publishing, installing, and reuse counts. Defer public publishing, cross-company telemetry, global rankings, publisher verification, and security scanning. If example listings or badges are shown, label them as examples rather than completed checks.

## 5. Product pages and scope

Build four initial UI areas after contracts stabilize:

1. Recruiter conversation with a review card.
2. Workforce list / agent profile, grouped by department and manager.
3. Manager Inbox for approve, reject, or request revision.
4. Company marketplace for publish, install, and creator reuse counts.

Keep run traces and basic performance statistics on the agent profile. Separate org chart visualization, leaderboard, admin console, and global marketplace pages can follow later.

**Must:** real hiring confirmation, persisted specs, real MCP execution, durable approval pause/resume, role checks, traces, and manager review.

**Next:** manual Intern → Associate promotion, company capability/agent publishing and install, local revalidation, reuse counts.

**Defer:** additional models such as Ollama, broad OAuth connector coverage, Senior/Lead behavior, automatic promotions, hourly savings claims, global analytics, and generated integrations.

## 6. Architecture

Frontend → Recruiter proposals and platform HTTP APIs → spec/registry, runtime/policy, reviews, and company marketplace modules → shared database, backend-only connection resolver, model provider, and MCP servers.

The Recruiter does not sit in the execution authorization path. Runtime policy and review services remain authoritative even if the model proposes an invalid capability or requests excessive permissions.

One shared runtime executes saved, versioned specs. Persist a proposed action and its exact arguments before waiting for approval. Resume only the approved immutable action, with a fresh policy/access check. Revised work requires a new review.

## 7. Three-minute demo

| Time | Demonstration |
| --- | --- |
| 0:00–0:15 | Explain repeated capability setup and the risk of granting autonomy too early |
| 0:15–0:55 | Ask Recruiter to hire a support agent from reusable company capabilities; confirm the Intern job card |
| 0:55–1:35 | Start a task; show it paused before a real tool call; manager approves; execution proceeds |
| 1:35–2:05 | Inspect evidence and trace; request revision on another proposed action |
| 2:05–2:30 | Manager promotes the agent to Associate; a permitted read runs without review |
| 2:30–2:50 | Publish/install an internal template; show the new install is an Intern and must bind authorized connections |
| 2:50–3:00 | Show creator reuse credit; close with “Describe the job. Hire the agent. Let it earn trust.” |

Use real operations with a small seeded dataset. Label sample content and any prerecorded backup explicitly. Do not claim seeded performance is live production evidence.

---

# Backend implementation and team ownership

## Product decision

Build the real loop: publish a reusable capability → Recruiter proposes a hire → manager confirms → Intern attempts a task → runtime pauses → manager approves or requests a revision → execution continues → manager promotes the agent → a later run follows the new permissions.

Do not add new product features until this loop works. Keep one company and one department initially. Start with a clean backend skeleton. Suggested baseline: Python, SQLite for the hackathon, a Gemini adapter, and MCP tools. Agree on the web framework and routing interface before implementation; all four members use the same stack. This document proposes contracts; these endpoints are not implemented by creating this plan.

## Improvements to the design

1. Use a backend-enforced permission matrix rather than trusting titles. For the MVP, implement Intern and Associate. Intern tool calls require review; Associate read calls can run automatically. Define low-risk writes explicitly; all other writes require review. Org policy can require stricter review at either level. Senior summaries and Lead delegation are roadmap items.
2. Make promotions manual and scoped. Approval counts are evidence for a manager, not automatic authority. Promotions cannot grant tools or connections the agent did not already have. Demotion affects the next action, including pending actions.
3. Treat the Recruiter as a proposal generator. It can choose catalog entries and draft specs, but only platform services validate, authorize, test, and commit them. The server binds a review card to a proposal revision so a changed plan cannot be confirmed using an old card.
4. Make approval pause real and persistent. Store the exact tool, arguments, agent/spec version, actor, policy decision, and connection reference before calling it. A revised action needs review again. Recheck current permissions immediately before execution.
5. Keep marketplace imports as portable recipes: instructions, capability IDs/versions, input/output schemas, and test definitions. No secrets, connection IDs, task history, approvals, or trust history cross installations. Rebind connections and retest locally. Agent templates install as Interns.
6. Separate capability test success, approved actions, and successful task outcomes. An approved action is not proof of a correct final task. Show counts and denominators. Do not call raw approval rate a security or accuracy score.
7. Label seeded marketplace content, badges, and metrics as examples. Do not claim a security scan or publisher verification happened if it did not. Defer global publishing, telemetry, and global rankings.

## Four branches and owners

| Member | Branch | Responsibility |
| --- | --- | --- |
| Amol | feat/registry-marketplace | Data layer, departments, capabilities, connections, internal marketplace |
| Tarun | feat/runtime-trust | Shared runtime, model/MCP adapters, policy evaluation, durable pause/resume |
| Shaun | feat/reviews-performance | Approval Inbox, manager decisions, promotions/demotions, honest metrics |
| You | feat/recruiter-integration | Recruiter proposals, hiring/spec versions, actor context, API assembly, integration/demo |

Do not have everyone edit the application entry point. Agree on a small routing interface first. Each owner registers their routes in their own module; you own the application entry point. Work in `backend/registry/`, `backend/runtime/`, `backend/reviews/`, and `backend/recruiter/`. Shared contracts live in `backend/contracts.py`. Amol owns database initialization; each person supplies their table migration in an assigned, separate migration file. Merge an initial contracts/data skeleton before parallel implementation.

### Amol: registry, persistence, and internal marketplace

Own tables for departments, users/role assignments, capabilities and versions, connection references, listings, and installs. Provide a connection resolver that returns a secret reference only to authorized backend callers. Provide one curated demo MCP connection through the same interface. No credential values in public API results.

Endpoints:

| Method | Path | Behavior |
| --- | --- | --- |
| GET | /api/departments | Departments visible to current actor |
| POST | /api/departments | Admin creates department; can be deferred when seeded |
| GET | /api/capabilities | Approved catalog with schemas, permissions, versions, test evidence |
| GET | /api/capabilities/{id} | Capability detail |
| POST | /api/capabilities | Admin registers a curated capability; arbitrary generated tools excluded |
| GET | /api/connections | Authorized connection metadata; no secrets |
| POST | /api/capabilities/{id}/validate | Run bounded test for the selected authorized connection; return validation ID and evidence |
| GET | /api/marketplace | Company listings; optional clearly labeled examples |
| POST | /api/marketplace | Publish an authorized portable capability/agent template internally |
| POST | /api/marketplace/{id}/install | Install a recipe; new agents start as Intern and require local connections/validation |

Acceptance: one capability is published and installed twice without copying secret references or trust; local connection access and validation are enforced. Show distinct installation count and creator attribution. Agent templates should call the same spec service as Recruiter hiring, not create a competing agent schema.

### Tarun: runtime and trust enforcement

Own tables for runs, run steps, and durable execution dispatch/outbox state. Own the sole path that actually calls a tool. Neither the Recruiter nor review endpoints execute tools directly. Implement real MCP transport and preserve model function-calling metadata during the tool loop.

Endpoints:

| Method | Path | Behavior |
| --- | --- | --- |
| POST | /api/agents/{id}/runs | Start a bounded run, returning run ID and current status |
| GET | /api/runs | Runs visible to actor; filter by agent/status |
| GET | /api/runs/{id} | Result, state, policy and approval references |
| GET | /api/runs/{id}/steps | Tool/model steps with duration and errors |
| POST | /api/runs/{id}/cancel | Stop before subsequent actions; do not imply an external action can be undone |

Internal interfaces:

- `evaluate_action(actor, agent, tool, args, connection) -> allow | require_approval | deny` with reason and policy revision.
- `start_run(agent_id, task, actor, idempotency_key) -> run`.
- `continue_after_review(approval_id) -> run`: callable only after the reviews service has recorded an authorized decision; not a public bypass endpoint.
- `cancel_run(run_id, actor) -> run`.

Run states: `queued`, `running`, `awaiting_approval`, `completed`, `failed`, `cancelled`. Review decisions must not resurrect completed/cancelled runs. Use durable queue/outbox or a recoverable dispatcher; a restart must not lose an approval wait. Idempotency keys prevent duplicate submissions; use provider idempotency where supported for writes. For uncertain external outcomes, record uncertainty rather than blindly retrying. Do not promise exactly-once execution for arbitrary external APIs.

Acceptance: with a fake counting tool, demonstrate zero calls before approval, one approved execution, no second execution on duplicate decision, rejection stops the run, and step limits are enforced. Repeat pause/restart/approve. Policy is reevaluated immediately before the resumed action.

### Shaun: Inbox, reviews, and permissions lifecycle

Own tables for approvals, review decisions, performance events, and audit events. Define the pending-action contract with Tarun before implementing. Only assigned manager or an authorized admin may decide or change autonomy; a Builder cannot approve their own hire through a client role field.

Endpoints:

| Method | Path | Behavior |
| --- | --- | --- |
| GET | /api/approvals | Actor's Inbox, filter by status |
| GET | /api/approvals/{id} | Exact action and argument snapshot, sources, agent/spec and policy revisions |
| POST | /api/approvals/{id}/decision | approve, reject, or request_revision with comment; transactionally consume pending review |
| POST | /api/agents/{id}/level | Authorized manager promotes/demotes with reason; backend applies permission matrix |
| GET | /api/agents/{id}/performance | Review counts, corrections, run outcomes, sample size |
| GET | /api/leaderboard | Company reuse count and review statistics with minimum sample size |
| GET | /api/audit | Read-only audit events for permitted actors; redact sensitive payloads |

For MVP, use request_revision with feedback rather than editing arbitrary tool JSON in the Inbox. A revised proposal receives a new approval ID. Approved/rejected decisions are immutable. Use a unique action/approval identity and conditional pending-to-decided update; dispatch continuation only once. Tarun owns execution itself.

Acceptance: wrong manager and Member get denied; duplicate approval does not dispatch again; rejection prevents the proposed action; requested revisions require fresh approval; promotion lets a read run without review but cannot bypass mandatory-write review. Metrics show explicit denominators and N/A for insufficient samples. Defer hours-saved estimates and global comparisons.

### You: Recruiter, agent specs, and integration

Own tables for conversations/messages, proposals, agent specs/versions. Own the application entry point/router and the shared contracts review. Establish actor context centrally; never accept the user's claimed role in a JSON body as authorization. A seeded local development identity is acceptable if visibly documented; it is not production authentication. Do not build OAuth plus five complete admin experiences this weekend.

Endpoints:

| Method | Path | Behavior |
| --- | --- | --- |
| GET | /api/me | Authenticated or clearly labeled local development actor, company, roles |
| POST | /api/recruiter/conversations | Start a setup conversation |
| POST | /api/recruiter/conversations/{id}/messages | Interpret job/capability request, ask for missing information, or return draft proposal |
| GET | /api/recruiter/proposals/{id} | Review card data with revision |
| POST | /api/recruiter/proposals/{id}/confirm | Role-checked, idempotent confirmation for exactly the reviewed revision |
| GET | /api/agents | Workforce list; frontend groups by department/manager/level for org chart |
| GET | /api/agents/{id} | Profile, current spec, capability/connection status |
| PATCH | /api/agents/{id} | Create a new spec revision for permitted edits; cannot directly elevate autonomy |
| GET | /api/agents/{id}/versions | Saved spec versions |

Confirmation requires assigned manager, permitted department, valid model profile, approved capability versions, authorized connections, and applicable local validation. If the actor is only a Builder, the hire stays a draft pending manager confirmation. Every new hire starts as Intern. The LLM cannot set an elevated level. Admin approval of a new catalog capability remains separate from manager approval of a hire.

Acceptance: the exact support-triage conversation creates a reviewable card and a real Intern on confirmation; incomplete inputs prompt for clarification; unsupported tools are rejected; duplicate confirmation produces one agent; changing the draft invalidates an older confirmation revision. Integrate Amol's registry, Tarun's runtime, and Shaun's approvals without duplicate definitions.

## Shared contract: agree before branching

Use UUID IDs, UTC timestamps, snake_case fields, and one error envelope:

```json
{"error":{"code":"permission_denied","message":"Only the assigned manager can approve this action.","details":{}}}
```

Suggested records:

- Actor: `user_id`, `org_id`, `roles`, allowed department IDs. Resolved server-side.
- Agent spec: `id`, `org_id`, `department_id`, `manager_id`, `name`, `job_description`, `instructions`, `model_profile_id`, capability/version references, authorized connection references, `level`, `spec_version`, `status`.
- Capability: `id`, `version`, `creator_id`, tool schemas and risk classes, config schema, input/output contracts, permission requirements, validation recipe. Risk classifications are server-controlled and org policy may raise them.
- Recruiter proposal: `id`, `kind`, `revision`, `status`, proposed values, missing fields, actor/org, validation references, confirmed resource ID.
- Proposed action: `id`, `run_id`, `agent_id`, `spec_version`, `tool_id`, tool/capability version, canonical arguments, connection reference, risk, policy revision.
- Approval: `id`, `action_id`, `assigned_manager_id`, `status`, immutable proposed-action snapshot/hash, decision actor/time/reason.
- Run step: `id`, `run_id`, sequence, kind, status, redacted input/output, timing, approval reference.
- Listing: `id`, `org_id`, portable template payload, publisher, scope (`company` for MVP), version, installation count. No connection IDs or run history in portable payloads.

Tool risk: `read`, `write`, `always_approve`. Risk comes from the approved catalog and org policy, never the model or request body. Level labels alone do not grant access. Pending action execution must match the approved immutable snapshot and recheck current connection and org permissions.

Use an `Idempotency-Key` header for hire confirmation, marketplace install, run submission, and approval decisions. Store the key with actor/org/operation and a payload hash. A replay of the same request returns the original result; reuse with a different payload is a conflict.

## Merge and integration order

1. You and Amol merge contracts, a minimal DB schema, actor context, and routing interface. All four branch from this common commit.
2. Each owner adds endpoints behind their module and includes request/response examples plus meaningful tests. Do not add a second web framework or rewrite the frontend while these contracts are moving.
3. Merge registry and a curated test connection. Recruiter can initially use a deterministic test adapter, clearly labeled, while the real Gemini path is implemented.
4. Merge runtime with a counting test tool and durable pause state, then wire reviews to continuation. The runtime and reviews owners should share one integration test.
5. Merge hiring confirmation and run the whole path through HTTP. This is the first demo checkpoint; UI can start from the frozen contracts now.
6. Add internal publish/install and creator reuse counts. Add a manual Intern → Associate promotion and rerun a read action.
7. Build only four initial screens: Recruiter + review card, workforce/profile, Inbox, company marketplace. A simple profile table covers performance; defer separate leaderboard/admin pages.
8. Rehearse a 3-minute story; freeze features. Clearly label any seeded examples.

## Final acceptance walkthrough

Hire a support agent as Intern → start a task → inspect pending action → confirm zero calls occurred → manager approves → actual MCP call executes → inspect trace → manager promotes to Associate → next permitted read runs without review → publish reusable template internally → install copy → copy starts Intern with no inherited connection permission or review history.

Keep demo fixtures read-only or use a local draft-ticket tool. Never rely on money movement, destructive deletion, real Slack messages, or code merging to demonstrate trust.
