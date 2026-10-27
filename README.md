# Hire an Agent (ORBIT)

**Describe a job, hire an AI agent for it, and let it earn trust.** Employees create scoped agents in plain English; managers approve what those agents may do; admins connect tools such as GitHub once, with tightly limited access, so everyone can share them safely.

Built at HackTX.

## Why

Everyone now has their own AI agents, and each person wires up their own connectors to GitHub and other tools for repetitive work. This platform makes that shared and governed: agents behave like team members, approved by a manager, using tools an admin has scoped.

## How it works

1. **Hire.** A user describes a job. The model (Meta Muse Spark or Gemini) returns a structured proposal: name, instructions and the tools the agent needs. The user reviews it and confirms.
2. **Run.** The agent works through a tool-calling loop. The model asks for a tool; **our server decides whether it is allowed**, pausing for manager approval where required.
3. **Approve.** Managers see the exact arguments and evidence in an Inbox before anything runs. Agents start as Interns (everything reviewed) and can be promoted to Associates.
4. **Share.** Approved agents are published to a company marketplace and installed by teammates as portable copies with no connections bound.
5. **Audit.** Every run, action, approval and outcome is stored durably, so runs survive restarts and the audit trail shows what the model asked for and what was approved.

## Tech stack

| Layer | Technology |
| --- | --- |
| AI | Meta Muse Spark (`muse-spark-1.3`) via the Model API; Google Gemini as an alternative |
| Backend | Python, FastAPI, Pydantic, Uvicorn |
| Data | SQLite with durable runs, approvals and audit events |
| Tools | MCP-style tool layer; GitHub connected through its hosted, read-only MCP endpoint |
| Frontend | Vanilla JavaScript, HTML and CSS (no build step) |
| Auth | Password accounts with HTTP-only session cookies, roles and rate limits |
| Delivery | Docker, Render, GitHub Actions |

## Quick start

Python 3.10+.

```sh
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env        # then add your keys locally
python server.py
```

Open http://localhost:8000 (API docs at `/docs`). Or double-click `run-arcade.command` on macOS.

## Configuration

Set values in `.env` (ignored by Git) or in your host's dashboard. Never commit keys.

| Variable | Purpose |
| --- | --- |
| `MODEL_API_KEY`, `META_MODEL` | Meta Model API key and model (default `muse-spark-1.3`) |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini key and model; `GEMINI_FALLBACK_MODELS` lists models to try when it is overloaded |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | Admin's fine-grained, read-only token for the GitHub tool |
| `AUTH_MODE=password` | Real sign-in (production requires it) |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Admin account created on first boot in production |
| `ALLOW_SIGNUP`, `SIGNUP_LIMIT`, `SIGNUPS_PER_HOUR` | Open sign-up for demos and its limits |

Check a model key without exposing it: `python scripts/check_model.py --provider meta`.

Demo mode needs no key. It is a labeled, deterministic workflow rather than an LLM.

## Model providers

Meta and Gemini run through one internal contract, so approval pauses and saved tool history work with either. Hiring retries temporary provider errors (including Meta's intermittent `404 model_not_found`), and Gemini falls back across models when one is busy. Failures log the provider's request ID, never the key.

## GitHub connector

GitHub is a **read-only** MCP adapter limited to `get_file_contents` and `list_issues`. The server holds one admin-provided token, so scope it to repositories the whole team may see. The admin connects it live from **Library → Add a tool**. It is not per-user OAuth and nothing writes to GitHub.

## Security

Authorization is enforced on the server; the UI only calls documented endpoints. Production mode refuses development identities, requires an HTTPS origin and a host check, and rate-limits sign-in and sign-up. Tool fetches block private and loopback addresses. See [docs/SECURITY-REVIEW.md](docs/SECURITY-REVIEW.md) for the review and remaining gaps.

## Tests

```sh
python -m unittest discover -s tests
node tests/test_frontend_contracts.js
```

Tests use real loopback MCP and FastAPI's test client with isolated databases, and mock provider responses.

## Deployment

A Docker image runs on Render (free plan: data resets on restart). See [docs/DEPLOY.md](docs/DEPLOY.md). Further docs: [API](docs/API.md), [operations](docs/OPERATIONS.md), [design](docs/DESIGN.md).

## Scope

Implemented: password sessions, two departments, ten curated capabilities, per-agent and per-action approval, Intern/Associate levels, durable pause and resume, a company marketplace, task outcomes and audit events.

Not implemented: SSO or OAuth, external customer systems, arbitrary MCP discovery, a public marketplace, distributed workers, or Slack and Teams connectors.

## Team

| Area | Owner |
| --- | --- |
| Registry, database, marketplace (`backend/registry/`, `backend/db.py`) | Amol |
| Runtime, model adapters, MCP (`backend/runtime/`) | Tarun |
| Reviews, levels, performance (`backend/reviews/`) | Shaun |
| Recruiter, app wiring (`backend/recruiter/`, `backend/app.py`) | Pavan |
