# Agent Builder Platform – Hackathon Plan

## 1. The Brief

> Building an AI agent often involves repeating the same setup: connecting tools, configuring models, writing instructions, and adding monitoring. How can a platform make that setup reusable so people can focus on what their agent should accomplish? Design and prototype a platform that lets users quickly create AI agents for enterprise-grade use.

**Our one-line pitch:** *Set it up once, reuse it everywhere. Builders only describe the goal.*

**Core idea:** An agent is just a saved config (a "spec") built from reusable blocks. One runtime can run any spec.

---

## 2. How We Answer the Brief

Each repeated setup step from the brief becomes a reusable block:

| Repeated setup | Our reusable block | How it works |
|---|---|---|
| Connecting tools | **Tool Catalog** | Admin connects each tool / MCP server once, credentials stored centrally. Builders just tick a box. |
| Configuring models | **Model Profiles** | Presets like "Fast" (Gemini Flash), "Private" (Ollama local), "Smart". Each bundles model, temperature, limits. |
| Writing instructions | **Instruction Templates** | Fill-in-the-blank templates (role, tone, task) + org-wide rules every agent inherits automatically. |
| Adding monitoring | **Built-in Observability** | Every agent gets tracing, cost tracking, and logs automatically. Zero setup. |

---

## 3. Architecture (from our whiteboard)

### Website pages
- **Build Agent page**
  - Choose capabilities (from existing MCP/tool catalog)
  - Choose model (Gemini API / Ollama API)
  - Write or pick instructions
  - Save agent
- **Add Capability**
  - Add MCP tool servers, skills, tools, instructions
  - Optional: separate "builder agent" that helps with this
- **Use Agent page** – chat with / run an agent
- **Shared Agents page** – browse, use, and clone agents others made
- **Traces page** – see what each run did (new, needed for monitoring)

### Backend
- **Agent runtime** – takes a prompt, calls the model, routes requests to tools (e.g. search internet, make reports), returns result
- **Storage**
  - Agent specs + versions
  - Repo / registry of MCP tools, servers, skills
  - Run traces and logs
- **Hosting** – deploy agent to a cloud/server; original page updates to show the new agent

### Flow
```
User → Build Agent page → picks blocks from catalog → saves Agent Spec
     → Runtime loads spec → Model (Gemini/Ollama) ↔ Tools (MCP)
     → Every step logged → Traces page
     → Share → teammate clones spec
```

---

## 4. The Agent Spec (shared contract – agree on this first!)

Everyone builds against this format. Frontend writes it, backend runs it.

```json
{
  "id": "support-triage",
  "name": "Support Ticket Triage",
  "version": 3,
  "owner": "alex@company.com",
  "description": "Summarizes new tickets and flags urgent ones",
  "model_profile": "fast",
  "instructions": {
    "template": "support-agent",
    "variables": { "tone": "professional", "team": "Customer Success" },
    "extra": "Flag any ticket mentioning outages as urgent."
  },
  "tools": ["web_search", "ticket_db", "slack_post"],
  "guardrails": {
    "requires_approval": ["slack_post"],
    "max_steps": 10,
    "max_cost_usd": 0.50
  },
  "visibility": "team"
}
```

**Model profile example**
```json
{ "id": "fast", "provider": "gemini", "model": "gemini-flash", "temperature": 0.3, "max_tokens": 2000 }
```

**Tool catalog entry example**
```json
{ "id": "web_search", "type": "mcp", "server_url": "...", "description": "Search the internet", "risk": "low" }
```

> Secrets (API keys) never go in the spec. They live in env vars / a secrets store.

---

## 5. Features & Priorities

### Must have (core demo)
- [ ] Agent spec format + storage
- [ ] Runtime that runs any spec end to end
- [ ] Model adapter: Gemini + Ollama behind one interface
- [ ] 2–3 real MCP tools (e.g. web search, file/DB, Slack or email)
- [ ] Build Agent page (pick blocks, save)
- [ ] Use Agent page (chat/run)

### Should have
- [ ] Traces view: each step, tool calls, latency, tokens, cost
- [ ] Templates gallery (Research agent, Support agent, etc.)
- [ ] Share + clone agents
- [ ] **Goal-to-agent generator:** user types a goal, builder agent drafts the spec from the catalog, user reviews and saves (our "wow" feature)

### Nice to have (enterprise polish)
- [ ] Roles (admin / builder / user) and per-agent tool permissions
- [ ] Human approval for risky tools
- [ ] Versioning with rollback
- [ ] Audit log (who built/changed/ran what)
- [ ] One-click deploy to a hosted endpoint

### Skip for now
- Full multi-cloud hosting
- Building our own big connector library

---

## 6. What Makes It "Enterprise-Grade"

Judges will look for these. Even partial versions help:
- **Monitoring** – traces + cost per run (easiest big win)
- **Access control** – roles + tool permissions per agent
- **Secrets handling** – central, never in specs
- **Guardrails** – step/cost limits, approval for risky actions
- **Versioning** – every save is a version, can roll back
- **Audit log** – full history
- **Model choice** – Ollama option = runs privately/on-prem

---

## 7. How We Beat Copilot Studio (for the pitch)

- One builder that scales simple → advanced (no confusing two-tool split)
- Model- and cloud-neutral (Gemini, Ollama, others)
- Monitoring built in from day one
- Open standards (MCP) – tools aren't locked in
- Predictable cost: cost limits + cost shown per run

---

## 8. Suggested Tech Stack

| Layer | Choice | Alt |
|---|---|---|
| Frontend | Next.js + Tailwind | Streamlit (if team is Python-heavy) |
| Backend | Python + FastAPI | Node/Express |
| Agent loop | Custom loop or LangGraph | — |
| Models | Gemini API + Ollama | — |
| Tools | MCP servers | — |
| Database | SQLite (hackathon) / Postgres | — |
| Monitoring | Log steps to our DB + trace UI | Langfuse |
| Hosting | Single server / Render / Railway / Vercel | — |

---

## 9. Suggested Team Split

Adjust to team size. Agree on the **spec format (Section 4) first** so everyone can work in parallel.

| Role | Owns |
|---|---|
| **Backend / Runtime** | Agent loop, model adapter (Gemini + Ollama), spec loading, guardrails |
| **Tools / MCP** | Tool catalog, 2–3 MCP servers, secrets handling |
| **Frontend** | Build page, Use page, Shared agents, Traces view |
| **Data / Monitoring** | DB schema, trace logging, cost tracking, versioning |
| **Pitch / Demo / PM** | Slides, demo script, templates, goal-to-agent prompt, testing |

---

## 10. Build Order

1. Agree on spec format + DB schema
2. Runtime runs one hardcoded agent end to end with one tool
3. Model adapter (Gemini + Ollama)
4. Tool catalog + model profiles
5. Build page + Use page connected to backend
6. Trace logging + Traces view
7. Templates + share/clone
8. Goal-to-agent generator
9. Enterprise polish (roles, approvals, versions)
10. Freeze features → rehearse demo

> Rule: always keep a working demo. Merge often, don't break main.

---

## 11. Demo Script (~3 minutes)

1. **Problem (20s):** Every agent repeats the same setup. Show the pain.
2. **Admin setup, done once (30s):** Show the tool catalog and model profiles already connected.
3. **Build fast (60s):** Build two different agents from the same blocks in under a minute each. Use the goal-to-agent generator for one.
4. **Run it (30s):** Run an agent on a real task.
5. **Monitoring (20s):** Open the trace: steps, tool calls, cost.
6. **Share (20s):** A teammate clones the agent and tweaks it.
7. **Close (20s):** "Set it up once, reuse it everywhere." Mention enterprise features.

**Backup:** Record a video of the demo in case Wi-Fi or APIs fail.

---

## 12. Open Questions for the Team

- [ ] Time limit: ______ Team size: ______
- [ ] Official judging criteria / required deliverables?
- [ ] Which 2–3 tools do we demo with?
- [ ] Next.js or Streamlit?
- [ ] Who has Gemini API keys? Who can run Ollama locally?
- [ ] What's our demo use case (support, research, sales, IT)?
- [ ] Do we need a deployed URL or is local OK?
