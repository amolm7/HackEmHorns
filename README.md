# Hire an Agent

Backend-first HackTX prototype: **describe a job, hire an Intern, review real tool actions, promote scoped reads, and reuse company capabilities.** The frontend is intentionally a plain workbench so a separate design skill can replace it later.

## Run

Python 3.10+ with FastAPI, Pydantic, and Uvicorn. No Node build step. Dependencies are pinned in `requirements.txt`; test dependencies are in `requirements-dev.txt`.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python server.py
```

Open **http://localhost:8000**. Database state persists in `data/workforce.sqlite3`. Start one application process per database. Use the VS Code `Run backend` task or run the command from its terminal.

Interactive API docs: **http://localhost:8000/docs**. OpenAPI JSON: **http://localhost:8000/openapi.json**. All 58 API operations are explicit FastAPI routes grouped into domain routers, with strict Pydantic request validation and documented headers. Swagger assets load from the standard jsDelivr CDN; the workbench has no CDN dependency.

The server binds to localhost. Set `AUTH_MODE=password` after provisioning an account with `scripts/create_user.py` for real username/password sign-in. Without that setting, the identity selector remains a **local development impersonation facility**. Production mode refuses development authentication. See [backend operations](docs/OPERATIONS.md) for setup, recovery, limits and deployment prerequisites.

## Live Meta AI

This project supports the Meta Model API at **dev.meta.ai**, not Facebook/Instagram Graph API tokens.

Copy `.env.example` to `.env` if necessary, then enter your key locally:

```dotenv
MODEL_API_KEY=your-local-key
META_MODEL=muse-spark-1.3
```

Restart the server. Select **muse-spark-1.3** in the Recruiter or execution mode selector. Set a model ID enabled for your account if it differs. Never paste keys into chat, job descriptions, or Git. `.env` is ignored. `META_API_KEY` is also accepted as an alternative environment variable.

### Team key setup

Share the Meta key through your team’s password manager. Each teammate should copy `.env.example` to `.env` only if they do not already have a `.env`, then set `MODEL_API_KEY` locally. Keep existing local settings when updating the key. Commit only the empty placeholders in `.env.example`; `.env`, other `.env.*` files, and `secrets/` are ignored by Git. The application reads credentials from `.env` or environment variables, so no secrets folder is needed.

To verify your configured Meta key without exposing it:

```sh
python scripts/check_model.py --provider meta
```

This makes real provider requests for structured output and a harmless test-tool round trip. It prints pass/fail, not your credentials. Account quota may be consumed.

An optional Gemini adapter is available through `GEMINI_API_KEY` and `GEMINI_MODEL`. Neither provider is required for sandbox checks. Credentials remain backend-only; prompts, instructions and retrieved sample data are sent to the selected live provider when using its mode.

**Demo mode is not an LLM.** It follows a labeled deterministic support workflow and executes real local MCP tools. It uses a fixed fictional login-outage draft; it does not promise to interpret arbitrary tasks. Demo setup handles structured fields and curated support requests; unsupported integrations are rejected. No fake live-AI fallback occurs on provider failure.

## Try the workflow

1. Keep identity **Pavan**, Support department, Pavan as manager, and demo mode.
2. Open **My agents → Hire agent**, describe a support triage job, and review the suggested setup. Confirm the hire.
3. Start the default task. The Intern pauses **before** calling the first tool.
4. Open **Inbox**, inspect the exact arguments and evidence, and approve. Repeat for document search and draft creation. These are distinct actions with distinct approvals.
5. Open the agent from **My agents**. Results appear under **Task & result**, with history and metrics under **Activity & performance**. Draft creation only saves a local draft; no message is sent.
6. In the agent’s **Settings**, promote it to Associate with a reason. On the next run, reads proceed automatically but draft creation still requires approval.
7. Publish the agent from **Library → Share with your team**, then install it from **Agent templates**. The copy starts Intern with no bound connections. Select the installed agent and validate/activate its local connections as its manager.
8. Record a task outcome separately from approving actions. Performance includes explicit denominators and is available within each agent’s profile.

For an automated HTTP walkthrough against a running server:

```sh
python scripts/demo.py
```

This creates labeled demo agents, runs, approvals and listings in the local database.

## Tests

```sh
python -m unittest discover -s tests -v
node --check static/app.js
node tests/test_frontend_contracts.js
```

Run commands inside the activated `.venv`. Tests use real loopback MCP and FastAPI TestClient with isolated temporary databases; the demo script additionally exercises live Uvicorn HTTP. Provider network responses are mocked for deterministic tests. They cover pause-before-call, authorization, duplicate/concurrent decisions, rejection, revision, restart recovery, local write deduplication, connection revocation, spec invalidation, trust reset, marketplace portability, metrics, model adapters, and transport errors. Mocked provider tests do not verify your credentials or live model availability.

## Modules / four work areas

| Original owner | Implementation |
| --- | --- |
| Amol | `backend/registry/`, `backend/db.py`: departments, catalog, connection resolver, validation, internal marketplace |
| Tarun | `backend/runtime/`: Gemini/Meta adapters, bundled MCP server/client, durable action policy and execution |
| Shaun | `backend/reviews/`: manager Inbox decisions, revisions, levels, performance, outcomes, audit/leaderboard reads |
| Pavan | `backend/recruiter/`, `backend/app.py`, `server.py`: conversations, review cards, hires, specs/versions, routing and integration |

FastAPI routers and Pydantic request models live in `backend/api/`. ASGI lifespan starts and closes the worker/MCP resources. Shared domain validation and authorization helpers live in `backend/contracts.py`. The basic UI talks exclusively to documented HTTP endpoints. Replace `static/` later without moving business logic into the browser.

See **docs/API.md** for all endpoints and payloads, and **docs/IMPLEMENTATION.md** for design decisions, recovery guarantees, and scope.

## Scope

Implemented: one seeded company, local actor roles, two departments, three curated capabilities, Intern/Associate, human approval with durable pause/resume, revisions, manual promotions/demotions, model function calls, company marketplace, portable installs, local validations, spec versions, task outcomes, traces, audit events, and measured reuse.

Not implemented: production login/OAuth/vault integrations, external customer systems, arbitrary MCP discovery, public/global marketplace, security certification/scanning, Senior summaries, Lead delegation, Ollama, streaming UI, dollar-cost accounting, or distributed workers. Connection resolution is backend-only for the bundled sandbox; no third-party account is connected. Fictional tickets/docs are explicitly labeled. Capability write validation checks discovery plus a read fixture; it does not silently perform an unreviewed write or certify general behavior.

References: [Meta tool calling](https://dev.meta.ai/docs/tool-calling), [Meta structured output](https://dev.meta.ai/docs/structured-output), [Meta quickstart](https://dev.meta.ai/docs/quickstart), [Gemini generateContent](https://ai.google.dev/api/generate-content), [MCP transport](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports).

## Workspace capabilities and design (latest)

- Preloaded capabilities: **Make a slideshow**, **Write a document**, **Analyze data**, **Research & summarize**, **Schedule meetings**, **Draft emails**, **Plan tasks** (plus the labeled support sandbox). Saving tools use risk `local_write`: agents set to "Runs alone" may read and save locally; anything else (e.g. reply drafts) always asks.
- Agent creation: choose a model, pick capabilities and/or describe the job, review, create. Agents start as "Asks first"; one switch moves them to "Runs alone". Follow-up questions continue a live conversation.
- Leaderboard: result quality (thumbs up/down on results), approval rate, capability usage and creator usage.
- `read_url` fetches only public http(s) pages (private/loopback addresses blocked, redirects re-checked). DNS-rebinding is not fully mitigated; do not expose this demo publicly.
- Design: "Mission control" (dark glass, 3D globe backdrop). See `docs/DESIGN.md`.


## Outcome-driven work queue

Open **Team work** (the default home page). Choose **Product launch**, **Growth analysis**, or **Decision brief**, or add a custom job with its source inputs and company constraints. The support queue remains under Other examples.

1. Load a fictional scenario. Repeated loads do not duplicate it.
2. Hire the suggested specialist or reuse an agent with the required capabilities. Company permissions and connection validation still apply.
3. Assign an owner and select Demo or an enabled live model. Demo uses explicitly labeled templates; live models produce original tool arguments. Analysis jobs in demo mode require CSV input.
4. Review restricted actions in Inbox. An Intern asks before every action; an Associate can read and save locally within existing permissions. Nothing is sent, published or purchased.
5. Review the deliverables together in Team work. Product launch requires analysis, a brief, and a deck before it can be accepted. Outcome review is separate from tool approval.
6. Mark work accepted or needing correction with notes. Corrected, failed, or cancelled work can be reassigned; the new attempt receives correction notes and prior runs remain in the agent audit trail.

Queue records and assignments persist in SQLite. Metrics show actual outcomes and execution turnaround, including time spent waiting for action review; they do not estimate hours saved. Sample intake is manual, with no email/CRM trigger or external routing integration. Routing labels are recommendations. API operations: `GET/POST /api/work-queue`, `POST /api/work-queue/sample-batch`, and per-item `/assign` and `/review`.

The redesigned UI uses atomic quick creation, durable task conversations, authenticated activity updates, and soft archiving. See `docs/BACKEND-NOTES.md` for the completed backend handoff and remaining scope.

### Skills (playbooks)

Every capability carries a short **skill**: a playbook for doing that kind of work well (for example, slide titles that state a takeaway, at most four short bullets, real numbers only; meeting titles that name the outcome, with a timed agenda). Live models receive the playbooks for the tools they hold, appended to the agent's instructions at run time, so updates apply to existing agents. The Library and each agent's About panel show them. Playbooks are guidance only: permissions, approvals and validation are unchanged.

- Slides accept `> ` lead statements, `stat: 38% | label` headline numbers, `notes: ` speaker notes, and a `theme` (aurora, paper, sunrise, mono). The viewer picks a layout (cover, statement, stats, list) per slide.
- `schedule_meeting` saves an invite with attendees, time, agenda and a downloadable `.ics` file. It cannot see calendars and sends nothing. `draft_email` saves an unsent draft and always asks for approval. `create_task_list` saves tasks with optional owner and due date.
- Demo mode reads obvious details from the request (emails, weekday or date, time, duration) and labels everything as a template.
