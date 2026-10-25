# Implementation status and engineering notes

All four backend work areas from the team plan have been implemented as modules behind FastAPI/Uvicorn. `backend/api/` contains explicit routers, strict Pydantic request contracts, common request dependencies, error handlers, transport middleware, and lifespan resource management. `/docs` and `/openapi.json` expose the actual route contract. The frontend uses the same HTTP contracts as the API documentation.

## Registry / marketplace

SQLite WAL-backed persistence; seeded roles, departments and ten capabilities; backend-only connection resolver; real MCP discovery/fixture validation; custom curated recipes; internal publishing and installs; portable payloads exclude connections and earned trust. No global marketplace or external OAuth/vault system is claimed.

## Runtime / trust

A single recoverable background dispatcher polls persisted queued/running runs. Agent spec versions, tool allowlists, department access, active connections, current org policy, maximum calls, and exact action hashes are enforced before dispatch. The default `agent` policy confirms a scoped agent once. The optional `action` policy pauses Intern tool calls for review; Associates may read and save local artifacts, while restricted tools require review. Organization-wide `require_all_approvals` overrides both modes. There are no public bypass/resume endpoints.

A pending action and approval are committed before execution. A decision marks a run queued in the same database transaction; a process crash cannot lose that continuation event. On startup, queued work resumes; approval waits remain persisted. Completed actions are not repeated. An action interrupted in `executing` may be retried with its original durable action ID **only because the bundled local draft tool implements a database deduplication ledger**. Reads are retryable. This is not an exactly-once guarantee for arbitrary external APIs; new integrations must supply provider idempotency or an explicit uncertain/manual-reconciliation state.

Cancellation cannot retract an already-started external action. For the bundled tools, cancellation rejects while a call is marked in flight, then can stop later work. Policy changes during that in-flight call apply to the next dispatch. Do not run multiple application worker processes against the same database; a distributed lease/queue is future work.

The bundled MCP client/server uses authenticated stateless Streamable HTTP with JSON responses, initialization, tool discovery, and tool calls. GET/SSE is intentionally unsupported (405). Only the application's private process token can access it. It is a concrete sandbox integration, not a universal external MCP client.

## Reviews / performance

Conditional state transitions and transactional idempotency prevent duplicate decisions from causing duplicate execution. Wrong managers and nonmanager roles cannot decide. Rejection stops the proposed action. Revision yields a new immutable action requiring fresh approval. Promotions/demotions are explicit manager decisions with audit reasons. Spec edits reset autonomy and invalidate outstanding old-spec actions.

Approval rates count reviewed actions; completed runs count execution outcomes; correctness uses separate explicit manager outcome records. Review denominators and a five-action ranking threshold are exposed. No invented hours-saved score or automatic trust promotion is used.

## Recruiter / spec integration

Conversations retain a versioned review proposal. The helper may draft only from approved capabilities; department, manager, connection, permission, and confirmation checks are deterministic platform services. Confirmation is restricted to manager/admin and starts the agent as Intern regardless of requested level. Builders can propose, but cannot self-confirm without the appropriate server-side role. Capability changes require an explicit new card and reset autonomy.

The local deterministic setup path is a development adapter, clearly labeled. Meta Model API uses structured output and Chat Completions function calls. Gemini uses generateContent and function declarations. Provider-native Meta assistant messages and Gemini function-call metadata are retained in private run context for replay across approval pauses. Meta Chat Completions does not retain cross-turn reasoning state; a future Responses adapter can add that capability if needed. Live Meta verification completed on October 24, 2026: authenticated structured output, function-call/result round trip, and a complete FastAPI Recruiter → Intern hire → approval pause → real MCP lookup → Meta final answer. The verification used fictional ticket T-101 and one explicitly approved read action. Gemini remains unverified with live credentials.

## Persistence and scale

Data is stored as versioned JSON records in named SQLite tables. This keeps the hackathon contract flexible; IDs and idempotency records are indexed by primary key. Lists are filtered by org/actor in service code. For production scale, migrate to typed relational tables, targeted SQL queries, schema migrations, enterprise identity federation, a deployment-grade secret manager, and an external work queue. Model setup calls currently hold a write transaction; this serializes concurrent setup mutations and should be separated into propose/validate/commit jobs before scaling.

## Frontend handoff

`static/index.html`, `static/app.js`, and `static/style.css` provide the visual workspace using `docs/API.md` contracts. Approval, risk, role, and state logic belongs on the backend. Retain the explicit demo identity/mode labels if using sandbox data; use password sessions for deployment; production mode refuses development identity selection.

## Verification

Activate `.venv` after installing `requirements-dev.txt`. Run `python -m unittest discover -s tests -v` and `python scripts/demo.py` against a running server. Automated tests isolate their databases and mock provider responses. The HTTP demo uses the actual worker and real loopback MCP. A live provider check is separate and needs the user's configured key; report that status accurately.

## FastAPI migration

The public standard-library request handler was replaced with FastAPI and Uvicorn. The private bundled MCP server remains a separate authenticated loopback protocol implementation. Domain services, SQLite data, and durable run/approval states remain compatible. Request validation now returns 422 for malformed bodies, unknown fields, wrong types and absent required replay headers. Error details omit input values. Documentation uses a nonce-protected Swagger initializer and a narrowly scoped CDN policy; the main workbench retains its self-only CSP. Password authentication is implemented; enterprise SSO and multi-process workers remain outside the MVP.

## Live provider verification

Meta Muse Spark (`muse-spark-1.3`) passed both `scripts/check_model.py --provider meta` and the full application workflow. Saved run ID: `00f3f0c0-392e-44f4-be62-e4e4e5f1dc99`. The final answer correctly identified T-101 as urgent. The Python installation initially lacked a suitable certificate trust bundle; the provider adapters now use the pinned `certifi` CA bundle with normal TLS certificate and hostname verification enabled. No secrets were printed or committed. The local `.env` remains Git-ignored.
