"use strict";
/* Hire an Agent — arcade cabinet frontend. Talks only to the documented /api endpoints. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = x => String(x ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const json = x => esc(JSON.stringify(x, null, 2));
const pct = x => x == null ? "--" : Math.round(x * 100) + "%";
const LEVELS = { intern: "LVL 1 · INTERN", associate: "LVL 2 · ASSOCIATE", senior: "LVL 3 · SENIOR" };
const TERMINAL = ["completed", "failed", "cancelled"];

let user = sessionStorage.getItem("dev-user") || "pavan";
let S = {};                       // cached server state
let busy = false;
let chat = { id: null, log: [], proposal: null };
let hireStep = "describe";
let libraryTab = "capabilities";
let librarySelection = null;
let hireDraft = freshHire();
const profileTabs = {}, profileMetrics = {}, taskDrafts = {};
function freshHire() { return { name: "Ticket Triage", message: "Hire an agent to triage urgent support tickets and draft replies.", department_id: "support", manager_id: null, mode: "demo", target_agent_id: "" }; }

async function api(path, method = "GET", body) {
  const headers = { "X-Dev-User": user };
  if (method !== "GET") { headers["Content-Type"] = "application/json"; headers["Idempotency-Key"] = crypto.randomUUID(); }
  const res = await fetch("/api/" + path, { method, headers, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Error(data.error?.message || `Request failed (${res.status}).`);
  return data;
}

async function load() {
  const paths = ["me", "dev/users", "departments", "capabilities", "model-profiles", "agents", "runs", "marketplace", "leaderboard"];
  const vals = await Promise.all(paths.map(p => api(p)));
  S = Object.fromEntries(paths.map((p, i) => [p, vals[i]]));
  S.approvals = await api("approvals").catch(() => []);
  S.proposals = await api("recruiter/proposals").catch(() => []);
  hud();
}

function hud() {
  $("#identity").innerHTML = S["dev/users"].map(u => `<option value="${esc(u.id)}" ${u.id === user ? "selected" : ""}>${esc(u.name)} · ${esc(u.roles.join("/"))}</option>`).join("");
  const pending = S.approvals.filter(a => a.status === "pending").length;
  $("#hud-roster").textContent = String(S.agents.length).padStart(2, "0");
  $("#hud-queue").textContent = String(pending).padStart(2, "0");
  const b = $("#menu-queue"); b.hidden = !pending; b.textContent = pending;
}

/* ---------- helpers ---------- */
const agentById = id => S.agents.find(a => a.id === id);
const userName = id => S["dev/users"].find(u => u.id === id)?.name || id || "--";
const deptName = id => S.departments.find(d => d.id === id)?.name || id || "--";
const isManager = () => S.me.roles.some(r => r === "manager" || r === "admin");
const opts = (list, sel) => list.map(([v, t, dis]) => `<option value="${esc(v)}" ${v === sel ? "selected" : ""} ${dis ? "disabled" : ""}>${esc(t)}</option>`).join("");
const deptOpts = sel => opts(S.departments.map(d => [d.id, d.name]), sel);
const mgrOpts = sel => opts(S["dev/users"].filter(u => u.roles.includes("manager") || u.roles.includes("admin")).map(u => [u.id, u.name]), sel ?? user);
const modelOpts = sel => opts(S["model-profiles"].map(m => [m.id, m.name + (m.enabled ? "" : " (key needed)"), !m.enabled]), sel);
const chip = (cls, text) => `<span class="chip ${cls}">${esc(text)}</span>`;
const lvlChip = l => chip("lvl-" + l, LEVELS[l] || l);
const stChip = s => chip("st-" + s, String(s).replace(/_/g, " ").toUpperCase());

function hash(str) { let h = 2166136261; for (const c of String(str)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
const SPRITE_COLORS = { intern: "#45e9ff", associate: "#ff8ad8", senior: "#ffcc1a" };
function sprite(id, level = "intern", size = 48) {
  // Original 8x8 mirrored pixel creature, seeded by agent id.
  let h = hash(id), rects = "";
  const color = SPRITE_COLORS[level] || "#bdb7ea";
  for (let y = 0; y < 8; y++) for (let x = 0; x < 4; x++) {
    h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0;
    const on = (y === 2 || y === 3) ? (x !== 1) : ((h & 3) !== 0);
    if (!on) continue;
    rects += `<rect x="${x}" y="${y}" width="1" height="1"/><rect x="${7 - x}" y="${y}" width="1" height="1"/>`;
  }
  return `<svg class="sprite" viewBox="0 0 8 8" width="${size}" height="${size}" fill="${color}" shape-rendering="crispEdges" aria-hidden="true">${rects}<rect x="2" y="3" width="1" height="1" fill="#05050d"/><rect x="5" y="3" width="1" height="1" fill="#05050d"/></svg>`;
}

let toastTimer;
function toast(msg, error = false) {
  const t = $("#toast"); t.textContent = msg; t.classList.toggle("error", error); t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, error ? 6000 : 3200);
}

async function act(fn, el) {
  if (busy) return; busy = true;
  const btns = $$("button", el?.closest("form") || el?.parentElement || document).filter(b => !b.disabled);
  btns.forEach(b => b.disabled = true);
  try { const msg = await fn(); await load(); render(); if (msg) toast(msg); }
  catch (e) { await load().catch(() => {}); render(); toast(e.message, true); }
  finally { busy = false; btns.forEach(b => { if (b.isConnected) b.disabled = false; }); }
}

function levelUp(name, level) {
  const box = $("#levelup"), burst = $("#burst");
  $("#levelup-sub").textContent = `${name} → ${LEVELS[level] || level}`;
  burst.innerHTML = "";
  for (let i = 0; i < 16; i++) {
    const p = document.createElement("i"), a = (i / 16) * Math.PI * 2, r = 160 + (i % 3) * 40;
    p.style.setProperty("--dx", Math.cos(a) * r + "px"); p.style.setProperty("--dy", Math.sin(a) * r + "px");
    burst.appendChild(p);
  }
  box.classList.remove("on"); void box.offsetWidth; box.classList.add("on");
  setTimeout(() => box.classList.remove("on"), 1500);
}

/* ---------- routing ---------- */
function route() {
  const [raw, id] = location.hash.replace(/^#\/?/, "").split("/");
  const aliases = { arcade: "agents", queue: "inbox", shop: "library", scores: "agents" };
  return { name: aliases[raw] || raw || "agents", id };
}
function render() {
  const r = route(), section = ["hire", "agent"].includes(r.name) ? "agents" : r.name;
  $$("#menu a").forEach(a => { if (a.dataset.route === section) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  const views = { agents, hire, inbox, library, agent };
  $("#view").innerHTML = (views[r.name] || agents)(r.id);
  document.title = ({ agents: "My agents", hire: "Hire agent", inbox: "Inbox", library: "Library", agent: agentById(r.id)?.name || "Agent" }[r.name] || "My agents") + " · Hire an Agent";
}

const toolName = name => ({ search_tickets: "Search support tickets", search_docs: "Search help documents", create_draft: "Save reply draft" }[name] || name);
const canManage = a => a && (a.manager_id === user || S.me.roles.includes("admin"));
function rosterCard(a) {
  const pending = S.runs.some(r => r.agent_id === a.id && r.status === "awaiting_approval");
  const status = pending ? "awaiting_approval" : a.status;
  return `<a class="player" href="#/agent/${esc(a.id)}">${sprite(a.id, a.level, 48)}<h3>${esc(a.name)}</h3><span class="meta">${esc(deptName(a.department_id))} · ${esc(userName(a.manager_id))}</span><span class="row">${lvlChip(a.level)} ${stChip(status)}</span><span class="card-next">Open agent →</span></a>`;
}
function agents() {
  const pending = S.approvals.filter(a => a.status === "pending"), drafts = S.proposals.filter(p => p.status === "draft");
  return `<div class="screen">
    <section class="page-intro"><div class="title-row"><div><h2>My agents</h2><p class="lede">Choose an agent and give it a task.</p></div><a class="btn coin" href="#/hire">＋ Hire agent</a></div></section>
    ${pending.length ? `<a class="review-banner" href="#/inbox"><span class="pac-dot" aria-hidden="true"></span><span><strong>${pending.length} action${pending.length === 1 ? "" : "s"} need your review</strong><span class="muted"> Your agents are waiting for approval.</span></span><span>Open Inbox →</span></a>` : ""}
    <section class="maze stack"><div class="title-row"><h3>Your team</h3><span class="faint">${S.agents.length} agent${S.agents.length === 1 ? "" : "s"}</span></div>
      ${S.agents.length ? `<div class="roster">${S.agents.map(rosterCard).join("")}</div>` : emptyState("Hire your first agent", "Describe its job. Review the hire. Then give it a task.", `<a class="btn coin" href="#/hire">Hire agent</a>`)}</section>
    ${drafts.length ? `<details class="maze"><summary>Hiring drafts (${drafts.length})</summary><div class="stack">${drafts.map(p => `<div class="row between"><span>${esc(p.spec.name)} · ${esc(userName(p.spec.manager_id))}</span><button class="btn small" data-act="resume-draft" data-id="${esc(p.id)}">Review hire</button></div>`).join("")}</div></details>` : ""}
    <div class="journey" aria-label="How it works"><span><b>1</b> Hire an agent</span><span><b>2</b> Give it a task</span><span><b>3</b> Review its work</span></div>
  </div>`;
}

function emptyState(title, body, cta = "") {
  return `<div class="empty"><span class="blink">${sprite("empty-" + title, "intern", 56)}</span><h3>${esc(title)}</h3><p>${esc(body)}</p>${cta}</div>`;
}

function hire() {
  const draft = chat.proposal, reviewing = hireStep === "review" && draft;
  const manager = hireDraft.manager_id || (isManager() ? user : "pavan");
  const canHire = S.me.roles.some(r => ["admin", "manager", "builder"].includes(r));
  return `<div class="screen hire-flow"><a class="back-link" href="#/agents">← My agents</a><div class="title-row"><h2>${hireDraft.target_agent_id ? "Add a capability" : "Hire an agent"}</h2></div>
    <ol class="hire-progress" aria-label="Hiring steps"><li class="${reviewing ? "done" : "current"}"><b>${reviewing ? "✓" : "1"}</b> Describe the job</li><li class="${reviewing ? "current" : ""}"><b>2</b> Review & confirm</li></ol>
    ${reviewing ? `<p class="lede">Check the job, capabilities, and manager before confirming.</p>${hireCard(draft)}<button class="btn" data-act="edit-hire">← Change details</button>` : `<section class="maze stack"><h3>What should your agent do?</h3><p class="muted">Describe the job. The Recruiter will suggest capabilities for you to review.</p>
      <form class="stack" data-form="recruit"><label>JOB<textarea name="message" required placeholder="For example: read support tickets and draft replies…">${esc(hireDraft.message)}</textarea></label>
      <div class="setup-summary"><span>${esc(deptName(hireDraft.department_id))} · Manager: ${esc(userName(manager))}</span><span class="faint">${hireDraft.mode === "demo" ? "Demo mode · no AI calls" : esc(S["model-profiles"].find(m => m.id === hireDraft.mode)?.name || hireDraft.mode)}</span></div>
      <details><summary>Change setup</summary><div class="stack"><label>AGENT NAME<input name="name" value="${esc(hireDraft.name)}" required></label><div class="split"><label>DEPARTMENT<select name="department_id">${deptOpts(hireDraft.department_id)}</select></label><label>MANAGER<select name="manager_id">${mgrOpts(manager)}</select></label></div><label>MODEL<select name="mode">${modelOpts(hireDraft.mode)}</select><span class="hint">Demo uses sample support data. Select Meta for live AI.</span></label></div></details>
      <button class="btn coin" ${canHire ? "" : "disabled"}>Review suggested hire →</button>${canHire ? "" : '<p class="faint">Your role cannot hire. Choose a manager or builder identity.</p>'}
      </form>${chat.log.length ? `<details><summary>Recruiter conversation</summary><div class="chat">${chat.log.map(m => `<div class="bubble ${m.me ? "me" : "bot"}"><span class="who-line">${m.me ? esc(userName(user)) : "RECRUITER"}</span>${esc(m.text)}</div>`).join("")}</div></details>` : ""}
      ${draft?.missing_fields.length ? `<p class="st-pending">Still needed: ${esc(draft.missing_fields.join(", "))}. Update the setup above and submit again.</p>` : ""}</section>`}
  </div>`;
}
function hireCard(p) {
  const ready = !p.missing_fields.length, canConfirm = S.me.roles.includes("admin") || (S.me.roles.includes("manager") && p.spec.manager_id === user);
  const caps = p.spec.capability_ids.map(id => S.capabilities.find(c => c.id === id)?.name || id);
  return `<article class="card-hire"><div class="row between">${sprite(p.id, "intern", 48)}${chip("lvl-intern", "STARTS AS INTERN")}</div><h2>${esc(p.spec.name)}</h2><p>${esc(p.spec.job_description)}</p>
  <div class="hire-facts"><p><span class="faint">Department</span> ${esc(deptName(p.spec.department_id))}</p><p><span class="faint">Manager</span> ${esc(userName(p.spec.manager_id))}</p></div>
  <div><h3>Capabilities</h3><div class="row">${caps.map(c => chip("st-active", c)).join("")}</div></div>
  <p class="muted">${p.kind === "hire" ? "Your Intern will ask before using a tool. You decide when it can do more." : "Adding capabilities resets this agent to Intern, with approval required before every action."}</p>
  <p class="${ready ? "st-completed" : "st-pending"}">${ready ? "✓ Connection checks passed" : "Complete the missing setup fields first."}</p>
  <details><summary>Technical details</summary><pre>${json(p)}</pre></details>
  <button class="btn coin" data-act="confirm" data-id="${esc(p.id)}" data-rev="${p.revision}" ${ready && canConfirm ? "" : "disabled"}>${p.kind === "hire" ? "Confirm hire" : "Confirm capability changes"}</button>
  ${canConfirm ? "" : `<p class="faint">Waiting for ${esc(userName(p.spec.manager_id))} or an admin to confirm.</p>`}</article>`;
}
function inbox() {
  const pending = S.approvals.filter(a => a.status === "pending"), past = S.approvals.filter(a => a.status !== "pending");
  return `<div class="screen"><section class="page-intro"><h2>Inbox ${pending.length ? `(${pending.length})` : ""}</h2><p class="lede">Review what your agents want to do next.</p></section>
    ${pending.length ? pending.map(quest).join("") : `<section class="maze dim">${emptyState("You're all caught up", "Actions that need your approval will appear here.", '<a class="btn" href="#/agents">Go to My agents</a>')}</section>`}
    ${past.length ? `<details class="maze"><summary>Review history (${past.length})</summary><div class="stack">${past.slice().reverse().slice(0,20).map(a => `<div class="row between"><span>${esc(agentById(a.agent_id)?.name || "Agent")} · ${esc(toolName(a.action.tool_id))}</span>${stChip(a.status)}</div>`).join("")}</div></details>` : ""}</div>`;
}

function quest(a) {
  const ag = agentById(a.agent_id);
  const mine = a.assigned_manager_id === user || S.me.roles.includes("admin");
  return `<article class="quest pending"><div class="row between"><span class="who">${sprite(a.agent_id, ag?.level, 36)}<span><h3>${esc(ag?.name || "Agent")}</h3><span class="faint">wants to <b>${esc(toolName(a.action.tool_id))}</b></span></span></span>${chip("risk-" + a.policy.risk, String(a.policy.risk).replace(/_/g, " ").toUpperCase())}</div>
    <p class="muted">${esc(userName(a.assigned_manager_id))} is the assigned reviewer. Approval allows only this specific action.</p>
    <div class="action-arguments">${Object.entries(a.action.arguments).map(([key,value]) => `<div><span class="faint">${esc(({query:"Search for",ticket_id:"Ticket",body:"Draft reply"})[key] || key)}</span><p class="answer-text">${esc(typeof value === "string" ? value : JSON.stringify(value))}</p></div>`).join("")}</div>
    <details><summary>Sources and technical details</summary><button class="btn small" data-act="evidence" data-id="${esc(a.id)}">Load prior evidence</button><pre data-evidence="${esc(a.id)}">${json(a)}</pre></details>
    <form class="stack" data-form="decide" data-id="${esc(a.id)}">
      <label>NOTES<input name="comment" placeholder="Required when requesting changes"></label>
      <div class="row"><button class="btn ok" name="decision" value="approve" ${mine ? "" : "disabled"}>Approve</button><button class="btn warn" name="decision" value="request_revision" ${mine ? "" : "disabled"}>Request changes</button><button class="btn bad" name="decision" value="reject" ${mine ? "" : "disabled"}>Reject</button>
      ${mine ? "" : `<span class="faint">Assigned to ${esc(userName(a.assigned_manager_id))}.</span>`}</div>
    </form></article>`;
}

function library() {
  const templates = S.marketplace.filter(l => l.kind === "agent");
  let selection = "";
  if (librarySelection?.kind === "capability") {
    const c = S.capabilities.find(c => c.id === librarySelection.id);
    if (c) selection = `<section class="maze stack"><div class="title-row"><h3>Use ${esc(c.name)}</h3><button class="btn small" data-act="close-library-selection">Cancel</button></div><form class="stack" data-form="use-capability" data-id="${esc(c.id)}"><label>WHERE SHOULD IT GO?<select name="target_agent_id"><option value="">Hire a new agent</option>${S.agents.filter(canManage).map(a => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join("")}</select></label><p class="muted">You'll review the proposed setup before anything changes.</p><button class="btn coin">Continue →</button></form></section>`;
  } else if (librarySelection?.kind === "template") {
    const l = templates.find(l => l.id === librarySelection.id);
    if (l) selection = `<section class="maze stack"><div class="title-row"><h3>Use ${esc(l.payload.name)}</h3><button class="btn small" data-act="close-library-selection">Cancel</button></div><form class="stack" data-form="install" data-id="${esc(l.id)}"><div class="split"><label>DEPARTMENT<select name="department_id">${deptOpts("support")}</select></label><label>MANAGER<select name="manager_id">${mgrOpts()}</select></label></div><p class="muted">Your copy starts as an Intern. Connect and validate its capabilities before running a task.</p><button class="btn coin">Create agent from template</button></form></section>`;
  }
  return `<div class="screen"><section class="page-intro"><h2>Library</h2><p class="lede">Reuse capabilities and agent templates from your team.</p></section>
    <div class="tabs" role="group" aria-label="Library content"><button data-act="library-tab" data-tab="capabilities" aria-pressed="${libraryTab === "capabilities"}">Capabilities</button><button data-act="library-tab" data-tab="templates" aria-pressed="${libraryTab === "templates"}">Agent templates</button></div>${selection}
    <div class="library-grid">${libraryTab === "capabilities" ? S.capabilities.map(c => { const reuse = S.leaderboard.capability_reuse.find(r => r.capability_id === c.id)?.installations || 0; return `<article class="maze stack"><h3>${esc(c.name)}</h3><p class="muted">${esc(c.description)}</p><div class="row">${chip(c.tool_contracts.every(t => t.risk === "read") ? "risk-read" : "risk-always_approve", c.tool_contracts.every(t => t.risk === "read") ? "READ ONLY" : "APPROVAL REQUIRED")}</div><p class="faint">By ${esc(userName(c.creator_id))} · ${reuse} installs</p><button class="btn coin small" data-act="use-capability" data-id="${esc(c.id)}">Use capability</button><details><summary>Tools and permissions</summary><p>${c.tool_contracts.map(t => esc(toolName(t.name))).join(", ")}</p></details></article>`; }).join("") : templates.map(l => `<article class="maze stack"><h3>${esc(l.payload.name)}</h3><p class="muted">${esc(l.payload.job_description)}</p><p class="faint">By ${esc(userName(l.creator_id || l.publisher_id))} · ${l.installation_count} installs</p><button class="btn coin small" data-act="use-template" data-id="${esc(l.id)}">Use template</button><details><summary>Capabilities and permissions</summary><pre>${json(l.nutrition_label)}</pre></details></article>`).join("") || `<section class="maze dim">${emptyState("No templates yet", "Share an agent below to make its setup reusable.")}</section>`}</div>
    <details class="maze"><summary>Share with your team</summary><div class="stack share-options"><p class="muted">Publish an agent template or capability to the company library.</p><form class="row" data-form="publish-agent"><label>AGENT<select name="source_id">${S.agents.map(a => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join("")}</select></label><button class="btn" ${S.agents.length ? "" : "disabled"}>Share agent template</button></form><div class="stack">${S.capabilities.map(c => `<div class="row between"><span>${esc(c.name)}</span><button class="btn small" data-act="publish" data-kind="capability" data-id="${esc(c.id)}">Share capability</button></div>`).join("")}</div></div></details></div>`;
}

function resultView(r) {
  if (r.error) return `<p class="st-failed">${esc(r.error)}</p>`;
  if (!r.result) return `<p class="muted">${r.status === "awaiting_approval" ? "Waiting for approval before the next action." : r.status === "cancelled" ? "This task was cancelled." : "Your agent is working. Results will appear here."}</p>`;
  if (r.result.answer) return `<div class="answer-text">${esc(r.result.answer)}</div>`;
  return `<p class="muted">Demo result · real tool calls over sample data, no AI model.</p>${(r.result.tool_results || []).map(part => {
    const response = part.functionResponse?.response || {};
    if (response.tickets) return response.tickets.map(t => `<div class="result-item"><strong>${esc(t.id)} · ${esc(t.subject)}</strong><p>${esc(t.body)}</p><span class="faint">Priority: ${esc(t.priority)}</span></div>`).join("");
    if (response.documents) return response.documents.map(d => `<div class="result-item"><strong>${esc(d.title)} (${esc(d.id)})</strong><p>${esc(d.text)}</p></div>`).join("");
    if (response.draft_id) return `<div class="result-item"><strong>Reply draft · saved, not sent</strong><p class="answer-text">${esc(response.body)}</p></div>`;
    return "";
  }).join("")}`;
}
function taskCard(r, a, expanded = false) {
  return `<article class="quest"><div class="row between">${stChip(r.status)}<span class="faint">${esc(r.mode === "demo" ? "Demo" : r.mode === "meta" ? "Meta AI" : "Gemini")}</span></div><p>${esc(r.task)}</p>${expanded ? resultView(r) : ""}
    <div class="row">${r.status === "awaiting_approval" ? `<a class="btn coin small" href="#/inbox">Review in Inbox →</a>` : ""}<button class="btn small" data-act="replay" data-id="${esc(r.id)}">View activity</button>${!TERMINAL.includes(r.status) ? `<button class="btn small bad" data-act="cancel" data-id="${esc(r.id)}">Cancel task</button>` : ""}</div>
    ${expanded && ["completed","failed"].includes(r.status) && canManage(a) ? `<details><summary>Was this task successful?</summary><div class="row"><button class="btn small ok" data-act="outcome" data-id="${esc(r.id)}" data-ok="true">Yes, successful</button><button class="btn small bad" data-act="outcome" data-id="${esc(r.id)}" data-ok="false">Needs improvement</button></div></details>` : ""}<div data-replay="${esc(r.id)}"></div></article>`;
}
function agent(id) {
  const a = agentById(id);
  if (!a) return `<section class="maze">${emptyState("Agent not found", "It may not be available to this identity.", '<a class="btn" href="#/agents">Back to My agents</a>')}</section>`;
  const runs = S.runs.filter(r => r.agent_id === id).slice().reverse(), latest = runs[0], tab = profileTabs[id] || "task", metrics = profileMetrics[id];
  const draft = taskDrafts[id] || { task: "Triage the urgent login outage and draft a reply.", mode: a.model_profile_id || "demo" };
  let content;
  if (tab === "task") content = `<div class="split"><section class="maze stack"><h3>Give it a task</h3><form class="stack" data-form="run" data-id="${esc(id)}"><label>TASK<textarea name="task" required>${esc(draft.task)}</textarea></label><details><summary>Execution settings</summary><label>MODEL<select name="mode">${modelOpts(draft.mode)}</select></label></details><button class="btn coin" ${a.status === "active" ? "" : "disabled"}>Run task →</button></form></section><section class="maze stack"><h3>Latest result</h3>${latest ? taskCard(latest,a,true) : '<p class="muted">Run a task to see the result here.</p>'}</section></div>`;
  else if (tab === "activity") content = `<section class="maze stack"><div class="title-row"><h3>Performance</h3><button class="btn small" data-act="perf" data-id="${esc(id)}">${metrics ? "Refresh" : "Load performance"}</button></div>${metrics ? `<div class="stats"><div class="stat"><span>TASKS COMPLETED</span><b>${metrics.p.completed_runs}/${metrics.p.run_count}</b></div><div class="stat"><span>ACTIONS REVIEWED</span><b>${metrics.p.reviewed_actions}</b></div><div class="stat"><span>APPROVAL RATE</span><b>${pct(metrics.p.approval_rate)}</b></div><div class="stat"><span>TASKS SUCCESSFUL</span><b>${metrics.p.successful_tasks}/${metrics.p.evaluated_tasks}</b></div></div><p class="faint">Action approvals and manager-assessed task success are separate measures.</p><details><summary>Spec version history (${metrics.v.length})</summary><pre>${json(metrics.v)}</pre></details>` : '<p class="muted">Load this agent’s review and task statistics.</p>'}<h3>Task history</h3>${runs.map(r => taskCard(r,a)).join("") || '<p class="muted">No tasks yet.</p>'}</section>`;
  else content = `<section class="maze stack"><h3>Capabilities</h3><div class="row">${a.bindings.map(b => chip("st-active", S.capabilities.find(c => c.id === b.capability_id)?.name || b.capability_id)).join("")}</div><a class="btn" href="#/library">Find capabilities in Library →</a><div class="pellets"></div><h3>Autonomy</h3><p class="muted">Interns ask before every tool action. Associates can read on their own; saving a draft still requires approval.</p><form class="stack" data-form="level" data-id="${esc(id)}"><label>REASON<input name="reason" value="Reviewed its work and scoped permissions." required></label><button class="btn ${a.level === "intern" ? "coin" : "warn"}" name="level" value="${a.level === "intern" ? "associate" : "intern"}" ${canManage(a) ? "" : "disabled"}>${a.level === "intern" ? "Promote to Associate" : "Return to Intern"}</button></form>${canManage(a) ? "" : '<p class="faint">Only the assigned manager or an admin can change autonomy.</p>'}<details><summary>Technical agent configuration</summary><pre>${json(a)}</pre></details></section>`;
  return `<div class="screen"><a class="back-link" href="#/agents">← My agents</a><section class="page-intro"><div class="row">${sprite(id,a.level,50)}<div class="stack"><h2>${esc(a.name)}</h2><div class="row">${lvlChip(a.level)} ${stChip(a.status)}</div></div></div><p class="lede">${esc(a.job_description)}</p><p class="faint">${esc(deptName(a.department_id))} · Managed by ${esc(userName(a.manager_id))}</p></section>
    ${a.status !== "active" ? `<section class="maze stack"><h3>Connect before the first task</h3><p class="muted">This agent needs its own validated connections. Trust and credentials aren't copied from a template.</p><button class="btn coin" data-act="activate" data-id="${esc(id)}" ${canManage(a) ? "" : "disabled"}>Connect and activate</button></section>` : ""}
    <div class="tabs" role="group" aria-label="Agent sections">${[["task","Task & result"],["activity","Activity & performance"],["settings","Settings"]].map(([key,label]) => `<button data-act="profile-tab" data-id="${esc(id)}" data-tab="${key}" aria-pressed="${tab === key}">${label}</button>`).join("")}</div>${content}</div>`;
}

/* ---------- events (delegated; CSP forbids inline handlers) ---------- */
document.addEventListener("click", e => {
  const b = e.target.closest("[data-act]"); if (!b) return;
  const { act: kind, id } = b.dataset;
  if (kind === "new-chat") { chat = { id: null, log: [], proposal: null }; hireDraft = freshHire(); hireStep = "describe"; render(); }
  if (kind === "library-tab") { libraryTab = b.dataset.tab; librarySelection = null; render(); }
  if (kind === "use-capability" || kind === "use-template") { librarySelection = { kind: kind === "use-capability" ? "capability" : "template", id }; render(); scrollTo({ top: 0 }); }
  if (kind === "close-library-selection") { librarySelection = null; render(); }
  if (kind === "profile-tab") { profileTabs[id] = b.dataset.tab; render(); }
  if (kind === "edit-hire") { hireStep = "describe"; hireDraft.message ||= chat.log.filter(m => m.me).at(-1)?.text || chat.proposal?.spec.job_description || ""; render(); }
  if (kind === "resume-draft") { const p = S.proposals.find(p => p.id === id); chat.proposal = p; hireStep = "review"; hireDraft = { ...freshHire(), ...p.spec, message: p.spec.job_description, mode: p.spec.model_profile_id, target_agent_id: p.target_agent_id || "" }; location.hash = "#/hire"; }
  if (kind === "evidence") (async () => { try { const detail = await api(`approvals/${id}`); $(`[data-evidence="${CSS.escape(id)}"]`).textContent = JSON.stringify(detail,null,2); } catch (err) { toast(err.message,true); } })();
  if (kind === "confirm") act(async () => { const a = await api(`recruiter/proposals/${id}/confirm`, "POST", { revision: Number(b.dataset.rev) }); chat = { id: null, log: [], proposal: null }; location.hash = "#/agent/" + a.id; return `${a.name} is ready. Give it a task to get started.`; }, b);
  if (kind === "publish") act(async () => { await api("marketplace", "POST", { kind: b.dataset.kind, source_id: id }); return "Shared with your team."; }, b);
  if (kind === "cancel") act(async () => { await api(`runs/${id}/cancel`, "POST", {}); return "Run cancelled."; }, b);
  if (kind === "outcome") act(async () => { await api(`runs/${id}/outcome`, "POST", { success: b.dataset.ok === "true", comment: "Manager reviewed the task output." }); return "Task result recorded."; }, b);
  if (kind === "activate") act(async () => {
    const a = agentById(id), ids = a.required_capabilities?.map(c => c.id) || a.bindings.map(x => x.capability_id), bindings = [];
    for (const cid of ids) { const v = await api(`capabilities/${cid}/validate`, "POST", { department_id: a.department_id, connection_id: "support-local" }); bindings.push({ capability_id: cid, connection_id: "support-local", validation_id: v.id }); }
    await api(`agents/${a.id}`, "PATCH", { bindings, expected_spec_version: a.spec_version });
    return "Connections validated.";
  }, b);
  if (kind === "replay") (async () => {
    const box = $(`[data-replay="${CSS.escape(id)}"]`);
    try { const steps = await api(`runs/${id}/steps`); box.innerHTML = steps.length ? `<ol class="timeline">${steps.map(s => `<li><span class="k">${esc(String(s.kind).toUpperCase())}</span><span>${esc(s.label)}</span></li>`).join("")}</ol><details><summary>Raw trace</summary><pre>${json(steps)}</pre></details>` : `<p class="faint">No steps yet.</p>`; }
    catch (err) { toast(err.message, true); }
  })();
  if (kind === "perf") (async () => {
    try { const [p,v] = await Promise.all([api(`agents/${id}/performance`),api(`agents/${id}/versions`)]); profileMetrics[id] = {p,v}; if(route().id === id) render(); }
    catch(err) { toast(err.message,true); }
  })();
});

document.addEventListener("submit", e => {
  const f = e.target, kind = f.dataset.form; if (!kind) return; e.preventDefault();
  const d = Object.fromEntries(new FormData(f)), sub = e.submitter;
  if (sub?.name) d[sub.name] = sub.value;
  if (kind === "recruit") act(async () => {
    if (!d.target_agent_id) delete d.target_agent_id;
    Object.assign(hireDraft,d);
    if (hireDraft.target_agent_id) d.target_agent_id = hireDraft.target_agent_id;
    if (hireDraft.capability_ids) d.capability_ids = hireDraft.capability_ids;
    d.connection_id = "support-local"; d.model_profile_id = d.mode;
    if (!chat.id) chat.id = (await api("recruiter/conversations", "POST", {})).id;
    chat.log.push({ me: true, text: d.message });
    try { const r = await api(`recruiter/conversations/${chat.id}/messages`, "POST", d); chat.proposal = r.proposal; hireStep = r.proposal.missing_fields.length ? "describe" : "review"; hireDraft.name = r.proposal.spec.name; chat.log.push({ me: false, text: r.message }); }
    catch (err) { chat.log.push({ me: false, text: "Couldn't draft that: " + err.message }); throw err; }
  }, sub);
  if (kind === "decide") {
    if (d.decision === "request_revision" && !d.comment.trim()) { toast("Describe what should change before requesting a revision.", true); f.comment.focus(); return; }
    act(async () => { await api(`approvals/${f.dataset.id}/decision`, "POST", d); return { approve: "Approved. The agent continues.", reject: "Rejected. That move won't run.", request_revision: "Changes requested. The revised action will need fresh approval." }[d.decision]; }, sub);
  }
  if (kind === "run") act(async () => { await api(`agents/${f.dataset.id}/runs`, "POST", { task: d.task, mode: d.mode, max_steps: 8 }); return "Task started. Any action needing approval will appear in your Inbox."; }, sub);
  if (kind === "level") act(async () => { const a = agentById(f.dataset.id); await api(`agents/${a.id}/level`, "POST", { level: d.level, reason: d.reason }); if (d.level !== "intern") levelUp(a.name, d.level); return d.level === "intern" ? `${a.name} now requires approval before every action.` : null; }, sub);
  if (kind === "publish-agent") act(async () => { await api("marketplace", "POST", { kind: "agent", source_id: d.source_id }); return "Agent template shared in the Library."; }, sub);
  if (kind === "use-capability") {
    const c = S.capabilities.find(c => c.id === f.dataset.id);
    hireDraft = { ...freshHire(), name: c.name + " agent", message: d.target_agent_id ? `Add ${c.name} to this agent.` : `Hire an agent that uses ${c.name}.`, target_agent_id: d.target_agent_id || "", capability_ids: [c.id] };
    chat = { id: null, log: [], proposal: null }; hireStep = "describe"; location.hash = "#/hire";
  }
  if (kind === "install") act(async () => { const r = await api(`marketplace/${f.dataset.id}/install`, "POST", d.department_id ? d : {}); if (r.resource?.level) location.hash = "#/agent/" + r.resource.id; return "Agent created as an Intern. Connect its capabilities before running a task."; }, sub);
});

$("#identity").addEventListener("change", e => { user = e.target.value; sessionStorage.setItem("dev-user", user); chat = { id: null, log: [], proposal: null }; hireDraft = freshHire(); hireStep = "describe"; librarySelection = null; act(async () => `Using ${userName(user)}’s workspace.`); });
document.addEventListener("input", rememberDraft);
document.addEventListener("change", rememberDraft);
function rememberDraft(e) {
  const form = e.target.closest("form");
  if (form?.dataset.form === "recruit") Object.assign(hireDraft,Object.fromEntries(new FormData(form)));
  if (form?.dataset.form === "run") taskDrafts[form.dataset.id] = Object.fromEntries(new FormData(form));
}
addEventListener("hashchange", () => { render(); scrollTo({ top: 0 }); });

// XP bars animate via transform once rendered (CSSOM, allowed by CSP).
new MutationObserver(() => $$("[data-xp]").forEach(i => { i.style.transform = `scaleX(${i.dataset.xp})`; })).observe($("#view"), { childList: true });

(async () => { try { await load(); render(); } catch (e) { $("#view").innerHTML = `<section class="maze">${emptyState("Workspace unavailable", "Start the server, then reload to reconnect.")}</section>`; toast(e.message, true); } })();

// Light polling so queue and runs stay live; skip while the player is typing or reading a trace.
setInterval(async () => {
  if (busy || document.hidden || !["agents", "inbox", "agent"].includes(route().name)) return;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) || $$("details[open]").length || $$("[data-replay] *").length) return;
  try { const before = JSON.stringify([S.runs, S.approvals, S.agents]); await load(); if (before !== JSON.stringify([S.runs, S.approvals, S.agents])) render(); } catch {}
}, 2500);
