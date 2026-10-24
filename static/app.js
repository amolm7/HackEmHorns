"use strict";
/* Hire an Agent: mission-control frontend. Talks only to the documented /api endpoints.
   Strict CSP: no inline handlers or styles, so events are delegated and dynamic styling goes through CSSOM. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = x => String(x ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const json = x => esc(JSON.stringify(x, null, 2));
const pct = x => (x == null ? "--" : Math.round(x * 100) + "%");
const TERMINAL = ["completed", "failed", "cancelled"];

/* ---------- icons: one authored set, one stroke weight ---------- */
const ICONS = {
  slides: ["M3 5h18v11H3z", "M8 20h8", "M12 16v4"],
  document: ["M6 3h8l4 4v14H6z", "M14 3v4h4", "M9 12h6", "M9 16h6"],
  chart: ["M3 20h18", "M6 20v-7", "M11 20V5", "M16 20v-9", "M21 20v-4"],
  search: ["M11 17a6 6 0 1 0 0-12 6 6 0 0 0 0 12z", "M16 16l5 5"],
  ticket: ["M3 8a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4z", "M14 6v12"],
  book: ["M5 4h13v15H7a2 2 0 0 0-2 2z", "M5 4v17"],
  reply: ["M9 7L4 12l5 5", "M4 12h9a7 7 0 0 1 7 7v1"],
  tool: ["M14.5 6.5a4 4 0 0 0-5 5L4 17l3 3 5.5-5.5a4 4 0 0 0 5-5l-2.5 2.5-2.5-.5-.5-2.5z"],
  plus: ["M12 5v14", "M5 12h14"],
  inbox: ["M4 13l2-8h12l2 8", "M4 13v6h16v-6", "M4 13h4l1 2h6l1-2h4"],
  trophy: ["M8 4h8v5a4 4 0 0 1-8 0z", "M8 6H5a3 3 0 0 0 3 4", "M16 6h3a3 3 0 0 1-3 4", "M12 13v4", "M8 20h8", "M9.5 17h5"],
  library: ["M4 4h5v16H4z", "M11 4h5v16h-5z", "M18 6l3 .8-3.5 13.2-3-.8z"],
  agents: ["M4 4h6v6H4z", "M14 4h6v6h-6z", "M4 14h6v6H4z", "M14 14h6v6h-6z"],
  check: ["M5 12.5l4.5 4.5L19 7"],
  x: ["M6 6l12 12", "M18 6L6 18"],
  up: ["M7 11v9H4v-9z", "M7 11l4-7c1.5 0 2.5 1 2.5 2.5V9h5a2 2 0 0 1 2 2.3l-1 6a2 2 0 0 1-2 1.7H7"],
  down: ["M17 13V4h3v9z", "M17 13l-4 7c-1.5 0-2.5-1-2.5-2.5V15h-5a2 2 0 0 1-2-2.3l1-6A2 2 0 0 1 6.5 5H17"],
  send: ["M21 3L3 10.5l7 2.5 2.5 7z", "M21 3L10 13"],
  bolt: ["M13 3L5 14h6l-1 7 8-11h-6z"],
  shield: ["M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z", "M9 12l2 2 4-4"],
  arrow: ["M5 12h14", "M13 6l6 6-6 6"],
  back: ["M15 6l-6 6 6 6"],
  next: ["M9 6l6 6-6 6"],
  copy: ["M9 9h10v11H9z", "M5 15V4h10"],
  model: ["M7 7h10v10H7z", "M10 3v4", "M14 3v4", "M10 17v4", "M14 17v4", "M3 10h4", "M3 14h4", "M17 10h4", "M17 14h4"],
  sparkle: ["M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"],
};
const icon = (name, cls = "") => `<svg class="ic ${cls}" viewBox="0 0 24 24" aria-hidden="true">${(ICONS[name] || ICONS.tool).map(d => `<path d="${d}"/>`).join("")}</svg>`;

/* ---------- state ---------- */
let user = sessionStorage.getItem("dev-user") || "pavan";
let S = { steps: {} };
let busy = false;
const wiz0 = () => ({ step: 1, mode: null, caps: [], text: "", name: "", dept: null, manager: null, proposal: null, chatId: null, target: "" });
let wiz = wiz0();
const ui = { slide: {}, board: "agents", rank: "results", lib: "capabilities", fresh: null, unlock: null, apart: {}, drafts: {}, metrics: {} };

async function api(path, method = "GET", body) {
  const headers = { "X-Dev-User": user };
  if (method !== "GET") { headers["Content-Type"] = "application/json"; headers["Idempotency-Key"] = crypto.randomUUID(); }
  const res = await fetch("/api/" + path, { method, headers, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Error(data.error?.message || `Request failed (${res.status}).`);
  return data;
}

async function load() {
  const paths = ["me", "dev/users", "departments", "capabilities", "model-profiles", "agents", "runs", "marketplace", "leaderboard", "work-queue"];
  const vals = await Promise.all(paths.map(p => api(p)));
  S = { ...S, ...Object.fromEntries(paths.map((p, i) => [p, vals[i]])) };
  S.approvals = await api("approvals").catch(() => []);
  S.proposals = await api("recruiter/proposals").catch(() => []);
  await loadSteps();
  chrome();
}
async function loadSteps() {
  const r = route();
  if (r.name !== "agent") return;
  await Promise.all(S.runs.filter(x => x.agent_id === r.id).map(async run => {
    if (S.steps[run.id]?.updated === run.updated_at) return;
    try { S.steps[run.id] = { updated: run.updated_at, list: await api(`runs/${run.id}/steps`) }; } catch { /* shown as empty */ }
  }));
}

/* ---------- lookups and small helpers ---------- */
const agentById = id => S.agents.find(a => a.id === id);
const capById = id => S.capabilities.find(c => c.id === id);
const userName = id => S["dev/users"].find(u => u.id === id)?.name || id || "--";
const deptName = id => S.departments.find(d => d.id === id)?.name || id || "--";
const isManager = () => S.me.roles.some(r => r === "manager" || r === "admin");
const canHire = () => S.me.roles.some(r => ["admin", "manager", "builder"].includes(r));
const canManage = a => !!a && (a.manager_id === user || S.me.roles.includes("admin"));
const profile = id => S["model-profiles"].find(m => m.id === id);
const modelLabel = id => (id === "demo" ? "Demo" : profile(id)?.name || id);
const alone = a => a.level !== "intern";
const defaultDept = () => S.me.department_ids[0] || "support";
const defaultManager = () => (isManager() ? user : "pavan");
const capsOf = a => (a.bindings.length ? a.bindings.map(b => b.capability_id) : (a.required_capabilities || []).map(c => c.id)).map(id => capById(id)).filter(Boolean);
const TOOL_VERB = { create_slideshow: "build a slideshow", create_document: "write a document", analyze_data: "analyze your data", read_url: "read a web page", search_tickets: "search support tickets", search_docs: "search help documents", create_draft: "save a reply draft" };
const RISK = { read: ["Reads only", "ok"], local_write: ["Saves in workspace", "ask"], always_approve: ["Always asks", "warn"] };
const pill = (cls, text) => `<span class="pill ${esc(cls)}">${esc(text)}</span>`;
const statusPill = s => pill(s, ({ queued: "Queued", running: "Working", awaiting_approval: "Needs review", completed: "Done", failed: "Stopped", cancelled: "Cancelled", active: "Ready", draft: "Needs confirmation", needs_connections: "Needs connecting" })[s] || String(s).replace(/_/g, " "));
const modePill = a => (alone(a) ? `<span class="pill alone">${icon("bolt", "sm")}Runs alone</span>` : `<span class="pill ask">${icon("shield", "sm")}Asks first</span>`);
const capChip = c => `<span class="cap">${icon(c.icon || "tool")}${esc(c.name)}</span>`;
const opts = (list, sel) => list.map(([v, t, dis]) => `<option value="${esc(v)}" ${v === sel ? "selected" : ""} ${dis ? "disabled" : ""}>${esc(t)}</option>`).join("");

function hash(str) { let h = 2166136261; for (const c of String(str)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
function orb(id, { size = 48, level = "intern", cls = "" } = {}) {
  const h = hash(id), hue = [168, 188, 206, 226, 250, 148][h % 6], gid = "o" + h, on = level !== "intern";
  return `<svg class="orb ${cls}" viewBox="-20 -20 40 40" width="${size}" height="${size}" aria-hidden="true"><defs><radialGradient id="${gid}" cx="36%" cy="30%" r="80%"><stop offset="0" stop-color="hsl(${hue} 100% 93%)"/><stop offset=".42" stop-color="hsl(${hue} 88% 62%)"/><stop offset="1" stop-color="hsl(${(hue + 50) % 360} 78% 24%)"/></radialGradient></defs><circle class="core" r="10.5" fill="url(#${gid})"/><ellipse class="ring" rx="18" ry="6.6" fill="none" stroke="${on ? "#4ff0c8" : "#8fb4ff"}" stroke-opacity="${on ? 0.95 : 0.65}" stroke-width="1.3" ${on ? "" : 'stroke-dasharray="3 3"'} transform="rotate(${-28 + (h % 5) * 6})"/></svg>`;
}

let toastTimer;
function toast(msg, error = false) {
  const t = $("#toast"); t.textContent = msg; t.classList.toggle("error", error); t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, error ? 7000 : 3400);
}

async function act(fn, el) {
  if (busy) return;
  busy = true;
  const btns = $$("button", el?.closest("form") || el?.parentElement || document).filter(b => !b.disabled);
  btns.forEach(b => { b.disabled = true; });
  try { const msg = await fn(); await load(); render(); if (msg) toast(msg); }
  catch (e) { await load().catch(() => {}); render(); toast(e.message, true); }
  finally { busy = false; btns.forEach(b => { if (b.isConnected) b.disabled = false; }); }
}

/* ---------- routing ---------- */
function route() {
  const [raw, id] = location.hash.replace(/^#\/?/, "").split("/");
  const alias = { arcade: "agents", hire: "create", queue: "inbox", scores: "leaderboard", shop: "library" };
  return { name: alias[raw] || raw || "work", id };
}
const TITLES = { work: "Team work", agents: "Agents", create: "Create an agent", inbox: "Inbox", leaderboard: "Leaderboard", library: "Library" };
function render() {
  const r = route(), section = r.name === "agent" ? "agents" : r.name;
  $$("#menu a").forEach(a => { if (a.dataset.route === section) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  const views = { work: workScreen, agents: agentsScreen, create: createScreen, agent: agentScreen, inbox: inboxScreen, leaderboard: leaderboardScreen, library: libraryScreen };
  $("#view").innerHTML = (views[r.name] || agentsScreen)(r.id);
  document.title = (r.name === "agent" ? agentById(r.id)?.name || "Agent" : TITLES[r.name] || "Agents") + " · Hire an Agent";
  if (ui.fresh) setTimeout(() => { ui.fresh = null; }, 900);
  if (ui.unlock) setTimeout(() => { ui.unlock = null; }, 700);
}
function enter() { const v = $("#view"); v.classList.remove("enter"); void v.offsetWidth; v.classList.add("enter"); setTimeout(() => v.classList.remove("enter"), 700); }

function chrome() {
  $("#identity").innerHTML = opts(S["dev/users"].map(u => [u.id, `${u.name} · ${u.roles.join("/")}`]), user);
  const pending = S.approvals.filter(a => a.status === "pending").length, b = $("#menu-queue");
  b.hidden = !pending; b.textContent = pending;
  const names = { work: "ticket", agents: "agents", inbox: "inbox", leaderboard: "trophy", library: "library" };
  $$("#menu a").forEach(a => { const svg = $("svg", a); if (svg && !svg.firstChild) { svg.setAttribute("viewBox", "0 0 24 24"); svg.innerHTML = ICONS[names[a.dataset.route]].map(d => `<path d="${d}"/>`).join(""); } });
  const c = $("#create-top"); if (!c.firstChild) c.innerHTML = `${icon("plus", "sm")}Create agent`;
}

/* ---------- screens ---------- */
function emptyState(title, body, cta = "") {
  return `<div class="empty">${orb("empty-" + title, { size: 76 })}<h2>${esc(title)}</h2><p>${esc(body)}</p>${cta}</div>`;
}

const JOBS = {
  launch: { name: "Product launch", caps: ["analyze-data", "write-document", "make-slideshow"], tools: ["analyze_data", "create_document", "create_slideshow"], deliverables: "Data analysis + decision brief + pitch deck", agent: "Launch strategist" },
  analysis: { name: "Growth analysis", caps: ["analyze-data"], tools: ["analyze_data"], deliverables: "Analysis + chart", agent: "Growth analyst" },
  brief: { name: "Decision brief", caps: ["write-document"], tools: ["create_document"], deliverables: "Decision document", agent: "Strategy associate" },
  support: { name: "Support response", caps: ["ticket-search", "help-docs", "reply-drafts"], tools: ["search_tickets", "search_docs", "create_draft"], deliverables: "Policy-backed reply draft", agent: "Support specialist" }
};
function workflowAgents(w) {
  return S.agents.filter(a => a.status === "active" && a.department_id === w.department_id && canManage(a) && w.required_tools.every(t => capsOf(a).some(c => (c.tools || []).includes(t))));
}
function workScreen() {
  const items = [...(S["work-queue"] || [])].sort((a,b) => Number(a.workflow === "support") - Number(b.workflow === "support")), finished = items.filter(w => w.finished_at);
  const accepted = items.filter(w => w.status === "accepted"), corrected = items.filter(w => w.status === "needs_correction");
  const seconds = finished.length ? Math.round(finished.reduce((n,w) => n + (Date.parse(w.finished_at)-Date.parse(w.assigned_at))/1000, 0)/finished.length) : null;
  return `<div class="screen"><div class="head"><div><h1>Give your team a mission.</h1><p class="muted">One job. Multiple deliverables. A named owner and a reviewable outcome.</p></div><a class="btn" href="#/library">Reuse a team template</a></div>
    <div class="queue-stats"><div class="panel"><b>${items.length}</b><span>Jobs received</span></div><div class="panel"><b>${items.filter(w=>w.status === "awaiting_approval").length}</b><span>Waiting for a decision</span></div><div class="panel"><b>${accepted.length} / ${accepted.length + corrected.length}</b><span>Outcomes accepted · ${corrected.length} need correction</span></div><div class="panel"><b>${seconds === null ? "—" : seconds + "s"}</b><span>Avg. execution turnaround · includes failed jobs and action review</span></div></div>
    <section class="panel stack"><div><h2>Start with a business outcome</h2><p class="muted">These examples use fictional inputs. Demo mode creates labeled templates; select a live model when assigning for original work. All outputs stay in the local workspace.</p></div><div class="mission-templates">${["launch","analysis","brief"].map(k=>`<button class="choice" data-act="load-job" data-workflow="${k}"><span class="body"><span class="title">${esc(JOBS[k].name)}</span><span class="sub">${esc(JOBS[k].deliverables)}</span></span>${icon("plus")}</button>`).join("")}</div><details><summary>Other examples</summary><button class="btn small" data-act="load-job" data-workflow="support">Load support tickets</button></details></section>
    <details class="panel plain"><summary>Create your own job</summary><form class="stack" data-form="create-job"><label class="field">Workflow<select name="workflow">${opts(["launch","analysis","brief"].map(k=>[k,JOBS[k].name]),"launch")}</select></label><label class="field">Team<select name="department_id">${opts(S.departments.map(d=>[d.id,d.name]),defaultDept())}</select></label><label class="field">Job title<input name="title" required maxlength="100" placeholder="Prepare our investor update"></label><label class="field">Brief, source data and company rules<textarea name="task" required maxlength="4000" placeholder="Include the inputs, required outputs and constraints. For analysis, paste CSV data."></textarea></label><button class="btn primary">Add to work queue</button></form></details>
    <div class="head"><h2>Work queue</h2><a class="btn small" href="#/inbox">Review actions in Inbox</a></div>
    ${!items.length ? emptyState("Your next mission starts here", "Choose a scenario above, or add a job with your own inputs and company rules.") : items.map(w => {
      const a = agentById(w.agent_id), canReview = a && canManage(a), id = esc(w.id), job = JOBS[w.workflow], eligible = workflowAgents(w);
      const state = {unassigned:"Unassigned",accepted:"Accepted",needs_correction:"Needs correction"}[w.status];
      return `<section class="panel stack"><div class="row between"><div><span class="pill">${esc(job.name)} · ${w.sample_data ? "Fictional input":"User-provided input"}</span><h2>${esc(w.title)}</h2></div>${state ? pill(w.status === "accepted" ? "ok":"ask",state) : statusPill(w.status)}</div>
      <p class="muted">${esc(job.deliverables)} · Reviewer: ${a ? esc(userName(a.manager_id)) : "Assigned agent’s manager"}</p>
      ${w.ticket ? `<p>${esc(w.ticket.body)}</p><p class="faint">Proposed routing: ${esc(w.route_to)} · recommendation only</p>` : `<details><summary>Brief & company rules</summary><pre>${esc(w.task)}</pre></details>`}
      <p class="faint">${a ? "Owner: " + esc(a.name) : "No agent assigned"}${w.run_id ? " · " + esc(modelLabel(S.runs.find(r=>r.id === w.run_id)?.mode)) : ""}</p>
      ${!w.run_id || ["needs_correction","failed","cancelled"].includes(w.status) ? `<div class="row"><button class="btn small" data-act="hire-workflow" data-workflow="${esc(w.workflow)}" data-dept="${esc(w.department_id)}">Hire ${esc(job.agent.toLowerCase())}</button></div><form class="row" data-form="assign-ticket" data-id="${id}"><label class="field">Assign owner<select name="agent_id" required>${opts(eligible.map(a=>[a.id,a.name]),"")}</select></label><label class="field">Execution<select name="mode">${opts(S["model-profiles"].filter(m=>m.enabled).map(m=>[m.id,m.id === "demo" ? "Demo · fixed templates" : m.name]),"demo")}</select></label><button class="btn primary" ${eligible.length ? "":"disabled"}>${w.run_id ? "Revise & rerun" : "Assign & start"}</button>${eligible.length ? "":"<span class='faint'>Hire or install an agent with the required capabilities first.</span>"}</form>` : `<div class="row"><a class="btn small" href="#/agent/${esc(w.agent_id)}">Open agent & audit trail</a>${w.status === "awaiting_approval" ? '<a class="btn primary small" href="#/inbox">Review next action</a>':""}</div>`}
      ${w.artifacts?.length ? `<details ${w.finished_at ? "open":""}><summary>Deliverables & evidence (${w.artifacts.length})</summary><div class="stack">${w.artifacts.map((x,i)=>artifactView(w.run_id + "-" + i,x)).join("")}</div></details>` : ""}
      ${w.error ? `<p class="warn">${esc(w.error)}</p>` : ""}
      ${w.finished_at && !w.outcome && ["completed","failed"].includes(w.status) && canReview ? `<form class="stack" data-form="review-ticket" data-id="${id}"><label class="field">Outcome notes<textarea name="comment" required placeholder="Do the deliverables meet the brief and company rules? What needs correction?"></textarea></label><div class="row"><button class="btn primary small" name="success" value="true" ${w.deliverables_ready && w.status === "completed" ? "":"disabled"}>Accept work</button><button class="btn small" name="success" value="false">Needs correction</button></div></form>`:""}
      ${w.outcome ? `<p><b>Manager outcome:</b> ${esc(w.outcome.comment)}</p>`:""}</section>`;
    }).join("")}</div>`;
}

function agentCard(a) {
  const waiting = S.runs.some(r => r.agent_id === a.id && r.status === "awaiting_approval");
  const row = S.leaderboard.agents.find(r => r.agent_id === a.id);
  const score = row?.result_eligible ? `${pct(row.task_success_rate)} good results` : row?.eligible ? `${pct(row.approval_rate)} approved` : "New";
  return `<a class="panel tilt agent-card" href="#/agent/${esc(a.id)}">
    <div class="row">${orb(a.id, { size: 52, level: a.level })}<div class="stack tight-gap"><h3>${esc(a.name)}</h3><span class="row">${waiting ? statusPill("awaiting_approval") : a.status !== "active" ? statusPill(a.status) : modePill(a)}</span></div></div>
    <p class="job">${esc(a.job_description)}</p>
    <div class="caps">${capsOf(a).slice(0, 3).map(capChip).join("")}</div>
    <div class="foot"><span>${esc(score)} · ${esc(modelLabel(a.model_profile_id))}</span><span class="go">Open ${icon("arrow", "sm")}</span></div></a>`;
}

function agentsScreen() {
  const pending = S.approvals.filter(a => a.status === "pending"), drafts = S.proposals.filter(p => p.status === "draft");
  return `<div class="screen">
    <div class="head"><div><h1>Your agents</h1><p class="muted">Assign recurring work from Team work, or open an agent for an individual request.</p></div></div>
    ${pending.length ? `<a class="banner" href="#/inbox">${icon("inbox")}<span><b>${pending.length} action${pending.length === 1 ? "" : "s"}</b> waiting for your review</span><span class="arrow">Open inbox ${icon("arrow", "sm")}</span></a>` : ""}
    ${S.agents.length ? `<div class="grid">${S.agents.map(agentCard).join("")}</div>` : `<div class="panel">${emptyState("No agents yet", "Choose a model, pick what it can do, and it is ready in under a minute.", canHire() ? `<a class="btn primary" href="#/create">${icon("plus", "sm")}Create your first agent</a>` : `<p class="faint">Switch to a manager or builder identity to create agents.</p>`)}</div>`}
    ${drafts.length ? `<details class="panel plain tight"><summary>${drafts.length} draft${drafts.length === 1 ? "" : "s"} waiting for confirmation</summary><div class="stack">${drafts.map(p => `<div class="row between"><span>${esc(p.spec.name)} <span class="faint">· ${esc(userName(p.spec.manager_id))} confirms</span></span><button class="btn small" data-act="resume-draft" data-id="${esc(p.id)}">Review</button></div>`).join("")}</div></details>` : ""}
  </div>`;
}

/* --- create wizard --- */
const EXAMPLES = ["Turn meeting notes into a short slide deck", "Summarize web pages I send it", "Analyze a CSV and call out what stands out", "Write one-page briefs from a few bullet points"];
function modelChoice(m) {
  const sub = m.id === "demo" ? "No AI model. Runs a fixed template so you can see the whole flow without an API key."
    : m.enabled ? "Writes original content, reads the pages you link, and answers follow-up questions."
    : `Add ${m.id === "meta" ? "MODEL_API_KEY" : "GEMINI_API_KEY"} to .env and restart the server to enable.`;
  return `<button type="button" class="choice" data-act="wiz-model" data-id="${esc(m.id)}" aria-pressed="${wiz.mode === m.id}" ${m.enabled ? "" : "disabled"}><span class="mark">${icon("check")}</span><span class="body"><span class="title">${esc(m.id === "demo" ? "Demo" : m.name)}${m.id === "demo" ? pill("ask", "Works offline") : pill("alone", m.id === "meta" ? "Meta" : "Google")}</span><span class="sub">${esc(sub)}</span></span></button>`;
}
function capChoice(c) {
  return `<button type="button" class="choice multi" data-act="wiz-cap" data-id="${esc(c.id)}" aria-pressed="${wiz.caps.includes(c.id)}"><span class="mark">${icon("check")}</span><span class="body"><span class="title">${icon(c.icon || "tool")}${esc(c.name)}</span><span class="sub">${esc(c.description)}</span></span></button>`;
}
function createScreen() {
  if (!wiz.mode) wiz.mode = S["model-profiles"].find(m => m.id !== "demo" && m.enabled)?.id || "demo";
  wiz.dept ||= defaultDept(); wiz.manager ||= defaultManager();
  const step = wiz.step, p = wiz.proposal;
  const workspace = S.capabilities.filter(c => (c.group || "Workspace") !== "Support sandbox"), support = S.capabilities.filter(c => c.group === "Support sandbox");
  const marks = ["Model", "Capabilities", "Review"].map((t, i) => `<li class="${step === i + 1 ? "current" : step > i + 1 ? "done" : ""}"><b>${step > i + 1 ? icon("check", "sm") : i + 1}</b>${t}</li>`).join("");
  let body = "";
  if (step === 1) {
    body = `<section class="panel stack"><div><h2>Choose a model</h2><p class="muted">This is the brain behind the agent. You can switch later.</p></div>
      <div class="stack">${S["model-profiles"].map(modelChoice).join("")}</div>
      <div class="row between"><span class="faint">${wiz.mode === "demo" ? "Demo content is a template. Pick a live model for real writing." : ""}</span><button class="btn primary" data-act="wiz-go" data-step="2">Continue ${icon("arrow", "sm")}</button></div></section>`;
  } else if (step === 2) {
    body = `<section class="panel stack"><div><h2>What should it be able to do?</h2><p class="muted">Pick one or more capabilities, or describe the job and the Recruiter will choose.</p></div>
      <div class="tiles">${workspace.map(capChoice).join("")}</div>
      ${support.length ? `<details><summary>Support sandbox capabilities (sample tickets)</summary><div class="tiles">${support.map(capChoice).join("")}</div></details>` : ""}
      <div class="or">or describe it</div>
      <label class="field">Describe the job<textarea data-draft="wiz-text" placeholder="For example: an assistant that turns meeting notes into a short deck">${esc(wiz.text)}</textarea></label>
      <div class="chips">${EXAMPLES.map(t => `<button type="button" class="chip-btn" data-act="wiz-example" data-text="${esc(t)}">${esc(t)}</button>`).join("")}</div>
      <details><summary>More options</summary><div class="split"><label class="field">Agent name<input data-draft="wiz-name" value="${esc(wiz.name)}" placeholder="Chosen for you"></label><label class="field">Manager (approves its work)<select data-draft="wiz-manager">${opts(S["dev/users"].filter(u => u.roles.includes("manager") || u.roles.includes("admin")).map(u => [u.id, u.name]), wiz.manager)}</select></label><label class="field">Department<select data-draft="wiz-dept">${opts(S.departments.map(d => [d.id, d.name]), wiz.dept)}</select></label></div></details>
      <div class="row between"><button class="btn ghost" data-act="wiz-go" data-step="1">${icon("back", "sm")}Back</button><button class="btn primary" data-act="wiz-draft" ${canHire() ? "" : "disabled"}>Continue ${icon("arrow", "sm")}</button></div>${canHire() ? "" : '<p class="faint">Your role cannot create agents. Switch to a manager or builder identity.</p>'}</section>`;
  } else if (p) {
    const confirmable = S.me.roles.includes("admin") || (S.me.roles.includes("manager") && p.spec.manager_id === user), upgrade = p.kind !== "hire";
    body = `<section class="panel stack review"><div class="row">${orb(p.id, { size: 56 })}<div><h2>${esc(p.spec.name)}</h2><p class="muted">${upgrade ? "Review the added capability" : "Ready to create"}</p></div></div>
      <dl><dt>Does</dt><dd>${esc(p.spec.job_description)}</dd><dt>Capabilities</dt><dd class="caps">${p.spec.capability_ids.map(id => capById(id)).filter(Boolean).map(capChip).join("")}</dd><dt>Model</dt><dd>${esc(modelLabel(p.spec.model_profile_id))}</dd><dt>Starts in</dt><dd>${modePill({ level: "intern" })} <span class="muted">${upgrade ? "Adding capabilities resets the agent to ask first." : "Every action waits for approval until you switch it."}</span></dd><dt>Approved by</dt><dd>${esc(userName(p.spec.manager_id))}</dd></dl>
      <details><summary>Technical details</summary><pre>${json(p)}</pre></details>
      <div class="row between"><button class="btn ghost" data-act="wiz-go" data-step="2">${icon("back", "sm")}Edit</button><button class="btn primary" data-act="wiz-confirm" data-id="${esc(p.id)}" data-rev="${p.revision}" ${confirmable ? "" : "disabled"}>${upgrade ? "Add capability" : "Create agent"}</button></div>
      ${confirmable ? "" : `<p class="faint">${esc(userName(p.spec.manager_id))} or an admin has to confirm this.</p>`}</section>`;
  }
  return `<div class="screen wizard"><a class="back" href="#/agents">${icon("back", "sm")}Agents</a><div class="head"><h1>${wiz.target ? "Add a capability" : "Create an agent"}</h1></div><ol class="steps" aria-label="Steps">${marks}</ol>${body}</div>`;
}

/* --- previews, results --- */
function parseOutline(text) {
  const slides = []; let cur = null;
  for (const raw of String(text).split("\n")) {
    const line = raw.trim(); if (!line) continue;
    if (line.startsWith("#")) { cur = { title: line.replace(/^#+\s*/, "") || "Untitled", bullets: [] }; slides.push(cur); }
    else { if (!cur) { cur = { title: "Overview", bullets: [] }; slides.push(cur); } cur.bullets.push(line.replace(/^[-*•]\s*/, "")); }
  }
  return slides;
}
function actionPreview(a) {
  const t = a.action.tool_id, g = a.action.arguments || {};
  let body = "";
  if (t === "create_slideshow") { const s = parseOutline(g.outline); body = `<h4>${esc(g.title)}</h4><div class="lines">${s.map((x, i) => `<span>${i + 1}. ${esc(x.title)} <span class="faint">· ${x.bullets.length} point${x.bullets.length === 1 ? "" : "s"}</span></span>`).join("")}</div>`; }
  else if (t === "create_document") body = `<h4>${esc(g.title)}</h4><div class="lines">${String(g.body).split("\n").filter(Boolean).slice(0, 8).map(l => `<span>${esc(l)}</span>`).join("")}</div>`;
  else if (t === "analyze_data") body = `<div class="kv"><span>Rows</span><span>${Math.max(0, String(g.table).trim().split("\n").length - 1)}</span>${g.question ? `<span>Question</span><span>${esc(g.question)}</span>` : ""}</div><pre>${esc(String(g.table).split("\n").slice(0, 4).join("\n"))}</pre>`;
  else if (t === "read_url") body = `<div class="kv"><span>Web page</span><span>${esc(g.url)}</span></div>`;
  else if (t === "create_draft") body = `<div class="kv"><span>Ticket</span><span>${esc(g.ticket_id)}</span><span>Draft</span><span>${esc(g.body)}</span></div>`;
  else body = `<div class="kv"><span>Search for</span><span>${esc(g.query)}</span></div>`;
  return `<div class="preview">${body}</div><details><summary>Exact data this approves</summary><pre>${json(g)}</pre></details>`;
}
function askCard(a) {
  const ag = agentById(a.agent_id), mine = a.assigned_manager_id === user || S.me.roles.includes("admin");
  const why = ag && alone(ag) ? "This action has effects beyond reading, so it always asks." : "This agent asks first. Approving covers only this one action.";
  return `<article class="panel ask-card stack"><div class="row between"><span class="row">${orb(a.agent_id, { size: 34, level: ag?.level })}<span><b>${esc(ag?.name || "Agent")}</b> <span class="muted">wants to ${esc(TOOL_VERB[a.action.tool_id] || a.action.tool_id)}</span></span></span>${pill("warn", "Needs you")}</div>
    <p class="why">${esc(why)}</p>${actionPreview(a)}
    <form class="decide" data-form="decide" data-id="${esc(a.id)}"><input name="comment" placeholder="Note for the agent (needed to send it back)" aria-label="Note for the agent">
      <div class="row"><button class="btn ok" name="decision" value="approve" ${mine ? "" : "disabled"}>${icon("check", "sm")}Approve</button><button class="btn warn" name="decision" value="request_revision" ${mine ? "" : "disabled"}>Send back</button><button class="btn bad" name="decision" value="reject" ${mine ? "" : "disabled"}>Reject</button>${mine ? "" : `<span class="faint">Assigned to ${esc(userName(a.assigned_manager_id))}.</span>`}</div></form></article>`;
}

function md(text) {
  const out = []; let list = [];
  const flush = () => { if (list.length) { out.push(`<ul>${list.map(x => `<li>${x}</li>`).join("")}</ul>`); list = []; } };
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  for (const raw of String(text).split("\n")) {
    const line = raw.trim();
    if (!line) { flush(); continue; }
    if (/^[-*•]\s+/.test(line)) { list.push(inline(line.replace(/^[-*•]\s+/, ""))); continue; }
    flush();
    if (/^#{1,3}\s/.test(line)) out.push(`<h4>${inline(line.replace(/^#+\s*/, ""))}</h4>`);
    else out.push(`<p>${inline(line)}</p>`);
  }
  flush(); return out.join("");
}

function slideViewer(runId, r) {
  const n = r.slides.length, i = Math.min(ui.slide[runId] || 0, n - 1), s = r.slides[i];
  return `<div class="result"><span class="result-label">${icon("slides", "sm")}Slideshow · ${n} slide${n === 1 ? "" : "s"} · saved in workspace, not published</span>
    <div class="stage ${i === 0 ? "cover" : ""}"><h3>${esc(i === 0 && !s.bullets.length ? r.title : s.title)}</h3>${s.bullets.length ? `<ul>${s.bullets.map(b => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}<span class="num">${i + 1} / ${n}</span></div>
    <div class="slidebar"><button class="btn small" data-act="slide" data-run="${esc(runId)}" data-to="${i - 1}" ${i === 0 ? "disabled" : ""} aria-label="Previous slide">${icon("back", "sm")}</button><button class="btn small" data-act="slide" data-run="${esc(runId)}" data-to="${i + 1}" ${i === n - 1 ? "disabled" : ""} aria-label="Next slide">${icon("next", "sm")}</button>
      <div class="thumbs">${r.slides.map((x, k) => `<button class="thumb" data-act="slide" data-run="${esc(runId)}" data-to="${k}" aria-current="${k === i}" aria-label="Slide ${k + 1}: ${esc(x.title)}">${k + 1}. ${esc(x.title)}</button>`).join("")}</div>
      <button class="btn small" data-act="copy" data-text="${esc(`${r.title}\n\n` + r.slides.map((x, k) => `${k + 1}. ${x.title}\n${x.bullets.map(b => "  - " + b).join("\n")}`).join("\n\n"))}">${icon("copy", "sm")}Copy text</button></div></div>`;
}
function chartSvg(c) {
  const pts = c.points; if (!pts.length) return "";
  const W = 520, H = 230, L = 10, B = 34, T = 22, max = Math.max(...pts.map(p => p.value), 1), bw = (W - L * 2) / pts.length, top = pts.reduce((m, p) => (p.value > m.value ? p : m), pts[0]);
  const bars = pts.map((p, i) => { const h = Math.max(2, (p.value / max) * (H - B - T)), x = L + i * bw + bw * 0.16, w = bw * 0.68, y = H - B - h; return `<rect class="bar ${p === top ? "" : "dim"}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" rx="3"/><text class="val" x="${(x + w / 2).toFixed(1)}" y="${(y - 6).toFixed(1)}" text-anchor="middle">${esc(p.value.toLocaleString(undefined, { maximumFractionDigits: 1 }))}</text><text x="${(x + w / 2).toFixed(1)}" y="${H - 14}" text-anchor="middle">${esc(String(p.label).slice(0, 9))}</text>`; }).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Bar chart of ${esc(c.y)} by ${esc(c.x)}"><line class="axis" x1="${L}" y1="${H - B}" x2="${W - L}" y2="${H - B}"/>${bars}</svg>`;
}
function analysisView(r) {
  const nums = Object.entries(r.numeric);
  return `<div class="result"><span class="result-label">${icon("chart", "sm")}Analysis · ${r.rows} rows · ${r.columns.length} columns</span>
    <div class="panel plain analysis"><div class="stack">${r.chart ? chartSvg(r.chart) : ""}</div><div class="stack"><ul class="highlights">${r.highlights.map(h => `<li>${esc(h)}</li>`).join("")}</ul>
    ${nums.length ? `<table class="data"><thead><tr><th>Column</th><th class="num">Mean</th><th class="num">Min</th><th class="num">Max</th></tr></thead><tbody>${nums.map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${v.mean.toLocaleString()}</td><td class="num">${v.min.toLocaleString()}</td><td class="num">${v.max.toLocaleString()}</td></tr>`).join("")}</tbody></table>` : ""}</div></div></div>`;
}
function docView(r) {
  return `<div class="result"><span class="result-label">${icon("document", "sm")}Document · ${r.word_count} words · saved in workspace, not published</span><article class="doc"><h3>${esc(r.title)}</h3>${md(r.body)}</article><div class="row"><button class="btn small" data-act="copy" data-text="${esc(`${r.title}\n\n${r.body}`)}">${icon("copy", "sm")}Copy text</button></div></div>`;
}
function artifactView(runId, x) {
  const r = x.result || {};
  if (r.kind === "slideshow") return slideViewer(runId, r);
  if (r.kind === "document") return docView(r);
  if (r.kind === "analysis") return analysisView(r);
  if (r.kind === "page_error") return `<div class="result"><span class="result-label">Page unavailable</span><div class="source"><p>${esc(r.error)}</p><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.url)}</a><p>The agent can continue using other sources.</p></div></div>`;
  if (r.kind === "page") return `<div class="result"><span class="result-label">${icon("search", "sm")}Read a web page</span><div class="source"><b>${esc(r.title)}</b><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.url)}</a><p>${esc(r.text.slice(0, 700))}${r.text.length > 700 ? "…" : ""}</p></div></div>`;
  if (r.draft_id) return `<div class="result"><span class="result-label">${icon("reply", "sm")}Reply draft · saved, not sent</span><div class="source"><b>Ticket ${esc(r.ticket_id)}</b><p>${esc(r.body)}</p></div></div>`;
  if (r.tickets) return `<div class="result"><span class="result-label">${icon("ticket", "sm")}Sample support tickets</span>${r.tickets.map(t => `<div class="source"><b>${esc(t.id)} · ${esc(t.subject)}</b><p>${esc(t.body)}</p><span class="faint">${esc(t.customer)} · ${esc(t.priority)}</span></div>`).join("")}</div>`;
  if (r.documents) return `<div class="result"><span class="result-label">${icon("book", "sm")}Sample help documents</span>${r.documents.map(d => `<div class="source"><b>${esc(d.title)} (${esc(d.id)})</b><p>${esc(d.text)}</p></div>`).join("")}</div>`;
  return "";
}

function runBody(r, a) {
  const steps = S.steps[r.id]?.list || [], arts = steps.filter(s => s.kind === "tool").map(s => ({ label: s.label, result: s.data.result }));
  const ask = S.approvals.find(x => x.run_id === r.id && x.status === "pending");
  let html = "";
  if (r.status === "awaiting_approval") html += ask ? askCard(ask) : `<div class="status">${statusPill("awaiting_approval")}Waiting for ${esc(userName(a.manager_id))} to approve.</div>`;
  else if (!TERMINAL.includes(r.status)) html += `<div class="status"><span class="dots"><i></i><i></i><i></i></span>${r.status === "queued" ? "Starting…" : "Working…"}</div>`;
  html += arts.map(x => artifactView(r.id, x)).join("");
  if (r.status === "completed" && r.result?.answer) html += `<div class="answer">${md(r.result.answer)}</div>`;
  if (r.status === "completed" && r.mode === "demo") html += `<p class="faint">Demo mode: real tools ran on a fixed template, no AI model. Choose a live model for original content.</p>`;
  if (r.status === "failed") html += `<div class="status">${statusPill("failed")}<span>${esc(r.error || "The task stopped.")}</span></div>`;
  if (r.status === "cancelled") html += `<div class="status">${statusPill("cancelled")}Cancelled.</div>`;
  if (["completed", "failed"].includes(r.status) && canManage(a)) {
    html += `<div class="rate">${r.outcome ? `${r.outcome.success ? "You rated this result good" : "You rated this result poor"}` : "Was this result good?"}
      <button data-act="rate" data-id="${esc(r.id)}" data-ok="true" class="${r.outcome?.success === true ? "on-up" : ""}" ${r.outcome ? "disabled" : ""} aria-label="Good result">${icon("up", "sm")}Good</button>
      <button data-act="rate" data-id="${esc(r.id)}" data-ok="false" class="${r.outcome?.success === false ? "on-down" : ""}" ${r.outcome ? "disabled" : ""} aria-label="Poor result">${icon("down", "sm")}Poor</button></div>`;
  }
  if (!TERMINAL.includes(r.status)) html += `<div class="row"><button class="btn small ghost" data-act="cancel" data-id="${esc(r.id)}">Cancel task</button></div>`;
  if (steps.length) html += `<details><summary>Activity (${steps.length})</summary><ol class="timeline">${steps.map(s => `<li><span class="k">${esc(String(s.kind).toUpperCase())}</span><span>${esc(TOOL_VERB[s.label] ? "Used: " + TOOL_VERB[s.label] : s.label)}</span></li>`).join("")}</ol></details>`;
  return html;
}

function followTarget(a, runs) {
  const last = runs.at(-1);
  return last && last.status === "completed" && last.mode !== "demo" && !ui.apart[a.id] ? last : null;
}
function agentScreen(id) {
  const a = agentById(id);
  if (!a) return `<div class="panel">${emptyState("Agent not found", "It may not be available to this identity.", `<a class="btn" href="#/agents">Back to agents</a>`)}</div>`;
  const runs = S.runs.filter(r => r.agent_id === id), follow = followTarget(a, runs), manages = canManage(a);
  const caps = capsOf(a), usable = profile(a.model_profile_id)?.enabled ? a.model_profile_id : "demo";
  const draft = ui.drafts[id] ?? "", ex = caps.map(c => c.example).filter(Boolean);
  let prev = null;
  const thread = runs.map(r => {
    const gap = prev && prev.thread_id !== r.thread_id ? `<div class="thread-gap">New conversation</div>` : ""; prev = r;
    return `${gap}<div class="turn"><div class="you">${esc(r.task)}</div><div class="reply">${orb(a.id, { size: 34, level: a.level })}<div class="out">${runBody(r, a)}</div></div></div>`;
  }).join("");
  const lb = S.leaderboard.agents.find(r => r.agent_id === id), m = ui.metrics[id];
  return `<div class="screen"><a class="btn small" href="#/work">Team work queue</a><a class="back" href="#/agents">${icon("back", "sm")}Agents</a>
    <div class="agent-head">${orb(a.id, { size: 72, level: a.level, cls: (ui.fresh === a.id ? "ignite " : "") + (ui.unlock === a.id ? "unlock" : "") })}
      <div class="meta"><div class="row between"><h1>${esc(a.name)}</h1>${a.status !== "active" ? statusPill(a.status) : ""}</div>
        <div class="row"><div class="seg" role="group" aria-label="Autonomy"><button data-act="mode" data-id="${esc(a.id)}" data-level="intern" aria-pressed="${!alone(a)}" ${manages ? "" : "disabled"}>${icon("shield", "sm")}Asks first</button><button data-act="mode" data-id="${esc(a.id)}" data-level="associate" data-tone="alone" aria-pressed="${alone(a)}" ${manages ? "" : "disabled"}>${icon("bolt", "sm")}Runs alone</button></div><span class="pill">${icon("model", "sm")}${esc(modelLabel(a.model_profile_id))}</span></div>
        <div class="caps">${caps.map(capChip).join("")}</div></div></div>
    ${a.status !== "active" ? `<section class="panel stack"><h2>Connect before the first task</h2><p class="muted">This agent needs its own validated connections. Trust and credentials never travel with a template.</p><div><button class="btn primary" data-act="activate" data-id="${esc(id)}" ${manages ? "" : "disabled"}>Validate and activate</button></div></section>` : ""}
    <div class="thread">${thread || `<div class="panel plain">${emptyState("Ask your first question", a.status === "active" ? "Give it a task below. " + (alone(a) ? "It will start right away." : "It will ask you before it acts.") : "Activate this agent first.")}</div>`}</div>
    <form class="composer" data-form="run" data-id="${esc(id)}">
      ${!runs.length && ex.length ? `<div class="chips">${ex.map(t => `<button type="button" class="chip-btn" data-act="example" data-id="${esc(id)}" data-text="${esc(t)}">${esc(t)}</button>`).join("")}</div>` : ""}
      <textarea name="task" data-draft="run" data-id="${esc(id)}" required placeholder="${follow ? "Ask a follow-up…" : "What should it do?"}" aria-label="Task" ${a.status === "active" ? "" : "disabled"}>${esc(draft)}</textarea>
      <div class="bar"><span class="row"><select name="mode" aria-label="Model for this task">${opts(S["model-profiles"].map(p => [p.id, p.id === "demo" ? "Demo (no AI)" : p.name + (p.enabled ? "" : " (key needed)"), !p.enabled]), usable)}</select>${follow ? `<button type="button" class="btn small ghost" data-act="new-thread" data-id="${esc(id)}">New conversation</button>` : ""}</span>
        <button class="btn primary" ${a.status === "active" ? "" : "disabled"}>${icon("send", "sm")}${follow ? "Ask" : "Send"}</button></div></form>
    <details class="panel plain"><summary>Agent details</summary><div class="stack"><div class="kv-list"><b>Job</b><p class="muted">${esc(a.job_description)}</p><b>Instructions</b><p class="muted">${esc(a.instructions)}</p></div>
      <div class="stack">${caps.flatMap(c => c.tool_contracts).map(t => `<div class="row"><b>${esc(TOOL_VERB[t.name] ? TOOL_VERB[t.name][0].toUpperCase() + TOOL_VERB[t.name].slice(1) : t.name)}</b>${pill((RISK[t.risk] || ["", ""])[1], (RISK[t.risk] || [t.risk])[0])}</div>`).join("")}</div>
      <div class="row"><button class="btn small" data-act="perf" data-id="${esc(id)}">${m ? "Refresh" : "Load"} performance</button><button class="btn small" data-act="share-agent" data-id="${esc(id)}">Share as template</button></div>
      ${m ? `<table class="data"><tbody><tr><td>Actions reviewed</td><td class="num">${m.p.reviewed_actions}</td></tr><tr><td>Approved</td><td class="num">${m.p.approved_actions}</td></tr><tr><td>Results rated good</td><td class="num">${m.p.successful_tasks} of ${m.p.evaluated_tasks}</td></tr><tr><td>Tasks finished</td><td class="num">${m.p.completed_runs} of ${m.p.run_count}</td></tr><tr><td>Spec versions</td><td class="num">${m.v.length}</td></tr></tbody></table>` : ""}
      <p class="faint">${esc(deptName(a.department_id))} · manager ${esc(userName(a.manager_id))} · spec v${a.spec_version}${lb ? " · " + (lb.reviewed_actions) + " actions reviewed" : ""}</p></div></details>
  </div>`;
}

function inboxScreen() {
  const pending = S.approvals.filter(a => a.status === "pending"), past = S.approvals.filter(a => a.status !== "pending");
  return `<div class="screen"><div class="head"><div><h1>Inbox</h1><p class="muted">Agents that ask first pause here. Approve one action at a time.</p></div></div>
    ${pending.length ? `<div class="stack">${pending.map(askCard).join("")}</div>` : `<div class="panel">${emptyState("You're all caught up", "Actions that need a person will show up here.", `<a class="btn" href="#/agents">Go to agents</a>`)}</div>`}
    ${past.length ? `<details class="panel plain tight"><summary>History (${past.length})</summary><div class="stack">${past.slice().reverse().slice(0, 25).map(a => `<div class="row between"><span>${esc(agentById(a.agent_id)?.name || "Agent")} <span class="muted">· ${esc(TOOL_VERB[a.action.tool_id] || a.action.tool_id)}</span></span>${pill(a.status === "approved" ? "ok" : a.status === "rejected" ? "bad" : "warn", a.status.replace(/_/g, " "))}</div>`).join("")}</div></details>` : ""}</div>`;
}

/* --- leaderboard --- */
function podiumCard(r, place, mode) {
  const a = agentById(r.agent_id), score = mode === "results" ? pct(r.task_success_rate) : pct(r.approval_rate), sub = mode === "results" ? `${r.successful_tasks} of ${r.rated_tasks} results good` : `${r.reviewed_actions} actions reviewed`;
  return `<a class="panel tilt pod ${place === 1 ? "first" : ""}" href="#/agent/${esc(r.agent_id)}"><span class="rank">#${place}</span>${orb(r.agent_id, { size: place === 1 ? 84 : 64, level: a?.level })}<span class="name">${esc(r.name)}</span><span class="score">${score}</span><span class="faint">${sub}</span>${a ? `<div class="caps">${capsOf(a).slice(0, 2).map(capChip).join("")}</div>` : ""}</a>`;
}
function leaderboardScreen() {
  const lb = S.leaderboard, tabs = [["agents", "Agents"], ["capabilities", "Capabilities"], ["creators", "Creators"]];
  let content = "";
  if (ui.board === "agents") {
    const mode = ui.rank, key = mode === "results" ? "result_eligible" : "eligible", need = mode === "results" ? lb.minimum_rated_tasks : lb.minimum_reviewed_actions;
    const val = r => (mode === "results" ? r.task_success_rate : r.approval_rate), count = r => (mode === "results" ? r.rated_tasks : r.reviewed_actions);
    const ranked = lb.agents.filter(r => r[key]).sort((x, y) => val(y) - val(x) || count(y) - count(x)), unranked = lb.agents.filter(r => !r[key]).sort((x, y) => count(y) - count(x));
    const order = [ranked[1], ranked[0], ranked[2]].map((r, i) => r && podiumCard(r, [2, 1, 3][i], mode)).filter(Boolean);
    const rest = ranked.slice(3);
    content = `<div class="row between"><div class="seg" role="group" aria-label="Rank by"><button data-act="rank" data-rank="results" aria-pressed="${mode === "results"}">Result quality</button><button data-act="rank" data-rank="approvals" aria-pressed="${mode === "approvals"}">Approval rate</button></div><span class="faint">${mode === "results" ? `Share of results managers rated good. Ranks after ${need} rated results.` : `Share of reviewed actions approved. Ranks after ${need} reviews.`}</span></div>
      ${order.length ? `<div class="podium">${order.join("")}</div>` : `<div class="panel">${emptyState("Nobody is ranked yet", mode === "results" ? `Rate an agent's results good or poor. Agents rank after ${need} rated results.` : `Agents rank after ${need} reviewed actions.`, `<a class="btn" href="#/agents">Go to agents</a>`)}</div>`}
      ${rest.length || unranked.length ? `<div class="panel"><table class="board"><thead><tr><th>Rank</th><th>Agent</th><th class="num">Score</th></tr></thead><tbody>${rest.map((r, i) => boardRow(r, String(i + 4), pct(val(r)), mode === "results" ? 1 : 1, count(r), need)).join("")}${unranked.map(r => boardRow(r, "--", "", 0, count(r), need)).join("")}</tbody></table></div>` : ""}`;
  } else if (ui.board === "capabilities") {
    content = lb.capability_usage.length ? `<div class="panel"><table class="board"><thead><tr><th>Rank</th><th>Capability</th><th>Creator</th><th class="num">Agents using it</th></tr></thead><tbody>${lb.capability_usage.map((r, i) => { const c = capById(r.capability_id); return `<tr><td class="rk">${i + 1}</td><td><span class="who">${icon(c?.icon || "tool")}${esc(c?.name || r.capability_id)}</span></td><td>${esc(userName(r.creator_id))}</td><td class="num"><b>${r.agents}</b></td></tr>`; }).join("")}</tbody></table></div>` : `<div class="panel">${emptyState("No usage yet", "Capabilities rank by how many active agents use them.", `<a class="btn" href="#/create">Create an agent</a>`)}</div>`;
  } else {
    content = lb.creator_usage.length ? `<div class="panel"><table class="board"><thead><tr><th>Rank</th><th>Creator</th><th class="num">Agents using their capabilities</th></tr></thead><tbody>${lb.creator_usage.map((r, i) => `<tr><td class="rk">${i + 1}</td><td><span class="who">${esc(userName(r.creator_id))}</span></td><td class="num"><b>${r.agents}</b></td></tr>`).join("")}</tbody></table></div>` : `<div class="panel">${emptyState("No creators yet", "Creators rank when agents use what they built.")}</div>`;
  }
  return `<div class="screen"><div class="head"><div><h1>Leaderboard</h1><p class="muted">Scores come from real manager decisions, not self-reports.</p></div><div class="seg" role="group" aria-label="Leaderboard">${tabs.map(([k, t]) => `<button data-act="board" data-tab="${k}" aria-pressed="${ui.board === k}">${t}</button>`).join("")}</div></div>${content}</div>`;
}
function boardRow(r, rank, score, ranked, n, need) {
  const a = agentById(r.agent_id);
  return `<tr><td class="rk">${rank}</td><td><a class="who" href="#/agent/${esc(r.agent_id)}">${orb(r.agent_id, { size: 32, level: a?.level })}${esc(r.name)}</a></td><td class="num"><span class="scorecell">${ranked ? `<b>${score}</b>` : `<span class="faint">${n} of ${need}</span><progress class="pending" max="${need}" value="${Math.min(n, need)}" aria-label="Progress to ranking"></progress>`}</span></td></tr>`;
}

/* --- library --- */
function libraryScreen() {
  const groups = ["Workspace", "Support sandbox", "Custom"].map(g => [g, S.capabilities.filter(c => (c.group || "Workspace") === g)]).filter(([, l]) => l.length);
  const usage = id => S.leaderboard.capability_usage.find(u => u.capability_id === id)?.agents || 0;
  const mine = S.agents.filter(canManage);
  const caps = groups.map(([g, list]) => `<div class="panel stack"><h2>${esc(g)}</h2><div class="list">${list.map(c => `<div class="item"><div class="main"><b class="row">${icon(c.icon || "tool")}${esc(c.name)}</b><span class="muted">${esc(c.description)}</span><span class="caps">${c.tool_contracts.map(t => pill((RISK[t.risk] || ["", ""])[1], (RISK[t.risk] || [t.risk])[0])).join("")}<span class="faint">by ${esc(userName(c.creator_id))} · ${usage(c.id)} agent${usage(c.id) === 1 ? "" : "s"} using it</span></span></div>
      <div class="acts"><button class="btn small" data-act="use-cap" data-id="${esc(c.id)}" ${canHire() ? "" : "disabled"}>${icon("plus", "sm")}New agent</button>${mine.length ? `<form class="row" data-form="add-cap" data-id="${esc(c.id)}"><select name="target_agent_id" aria-label="Add ${esc(c.name)} to">${opts(mine.map(a => [a.id, a.name]), "")}</select><button class="btn small">Add</button></form>` : ""}</div></div>`).join("")}</div></div>`).join("");
  const listings = S.marketplace.filter(l => l.kind === "agent");
  const shared = `<div class="panel stack"><div><h2>Shared agents</h2><p class="muted">Templates your team published. Installing copies the job and instructions, never credentials or earned trust.</p></div>
    ${listings.length ? `<div class="list">${listings.map(l => `<div class="item"><div class="main"><b>${esc(l.payload.name)}</b><span class="muted">${esc(l.payload.job_description)}</span><span class="faint">by ${esc(userName(l.creator_id || l.publisher_id))} · ${l.installation_count} install${l.installation_count === 1 ? "" : "s"}</span></div>
      <form class="acts" data-form="install" data-id="${esc(l.id)}"><select name="manager_id" aria-label="Manager">${opts(S["dev/users"].filter(u => u.roles.includes("manager") || u.roles.includes("admin")).map(u => [u.id, u.name]), defaultManager())}</select><button class="btn small primary" ${canHire() ? "" : "disabled"}>Install</button></form></div>`).join("")}</div>` : `<p class="faint">Nothing shared yet. Open an agent and choose “Share as template”.</p>`}</div>`;
  const add = `<details class="panel plain"><summary>Add a capability (admin)</summary><form class="stack" data-form="new-cap"><div class="split"><label class="field">Name<input name="name" required maxlength="100"></label><label class="field">What it does<input name="description" required maxlength="500"></label></div><div class="tools-pick" role="group" aria-label="Tools">${Object.entries(TOOL_VERB).map(([k, v]) => `<label><input type="checkbox" name="tools" value="${esc(k)}">${esc(v[0].toUpperCase() + v.slice(1))}</label>`).join("")}</div><div><button class="btn small primary" ${S.me.roles.includes("admin") ? "" : "disabled"}>Add capability</button> ${S.me.roles.includes("admin") ? "" : '<span class="faint">Only admins can add capabilities.</span>'}</div></form></details>`;
  return `<div class="screen"><div class="head"><div><h1>Library</h1><p class="muted">Capabilities your company set up once. Any allowed agent can plug them in.</p></div><div class="seg" role="group" aria-label="Library"><button data-act="lib" data-tab="capabilities" aria-pressed="${ui.lib === "capabilities"}">Capabilities</button><button data-act="lib" data-tab="agents" aria-pressed="${ui.lib === "agents"}">Shared agents</button></div></div>${ui.lib === "capabilities" ? caps + add : shared}</div>`;
}

/* ---------- events ---------- */
document.addEventListener("click", e => {
  const b = e.target.closest("[data-act]"); if (!b) return;
  const { act: kind, id } = b.dataset;
  if (kind === "load-job") act(async () => { await api("work-queue/sample-batch", "POST", { workflow: b.dataset.workflow }); return "Sample job loaded. Hire an owner or assign an existing agent."; }, b);
  if (kind === "hire-workflow") { const job = JOBS[b.dataset.workflow]; wiz = { ...wiz0(), step: 1, caps: job.caps, work: true, name: job.agent, text: `Own ${job.name.toLowerCase()} jobs. Produce ${job.deliverables.toLowerCase()}. Follow the job’s company rules, use source data and ask before acting. Never publish, send messages or spend money.`, dept: b.dataset.dept || defaultDept(), manager: defaultManager() }; location.hash = "#/create"; }
  if (kind === "wiz-model") { wiz.mode = id; render(); }
  if (kind === "wiz-go") { wiz.step = Number(b.dataset.step); render(); }
  if (kind === "wiz-cap") { wiz.caps = wiz.caps.includes(id) ? wiz.caps.filter(c => c !== id) : [...wiz.caps, id]; render(); }
  if (kind === "wiz-example") { wiz.text = b.dataset.text; render(); $("[data-draft='wiz-text']")?.focus(); }
  if (kind === "wiz-draft") act(async () => {
    if (!wiz.caps.length && !wiz.text.trim()) throw Error("Pick a capability or describe the job first.");
    const names = wiz.caps.map(c => capById(c)?.name).filter(Boolean).join(", ");
    const body = { message: wiz.text.trim() || `Create an agent that can: ${names}.`, department_id: wiz.dept, manager_id: wiz.manager, mode: wiz.caps.length ? "demo" : wiz.mode, model_profile_id: wiz.mode };
    if (wiz.caps.length) body.capability_ids = wiz.caps;
    if (wiz.name.trim()) body.name = wiz.name.trim();
    if (wiz.target) body.target_agent_id = wiz.target;
    if (!wiz.chatId) wiz.chatId = (await api("recruiter/conversations", "POST", {})).id;
    const r = await api(`recruiter/conversations/${wiz.chatId}/messages`, "POST", body);
    wiz.proposal = r.proposal; wiz.step = 3;
  }, b);
  if (kind === "wiz-confirm") act(async () => {
    const upgrade = wiz.proposal.kind !== "hire", a = await api(`recruiter/proposals/${id}/confirm`, "POST", { revision: Number(b.dataset.rev) });
    const destination = wiz.work ? "#/work" : "#/agent/" + a.id; wiz = wiz0(); ui.fresh = upgrade ? null : a.id; location.hash = destination;
    return upgrade ? `Capability added to ${a.name}. It asks first again.` : `${a.name} is ready. Assign a job from Team work.`;
  }, b);
  if (kind === "resume-draft") { const p = S.proposals.find(x => x.id === id); wiz = { ...wiz0(), step: 3, proposal: p, mode: p.spec.model_profile_id, caps: p.spec.capability_ids, target: p.target_agent_id || "" }; location.hash = "#/create"; }
  if (kind === "use-cap") { wiz = { ...wiz0(), caps: [id], step: 1 }; location.hash = "#/create"; }
  if (kind === "mode") { const a = agentById(id); if (a && (a.level === "intern") !== (b.dataset.level === "intern")) act(async () => { await api(`agents/${id}/level`, "POST", { level: b.dataset.level, reason: "Switched from the agent page." }); if (b.dataset.level !== "intern") ui.unlock = id; return b.dataset.level === "intern" ? `${a.name} asks before every action again.` : `${a.name} now runs alone for reads and local saves.`; }, b); }
  if (kind === "example") { ui.drafts[id] = b.dataset.text; render(); const t = $("[data-draft='run']"); t?.focus(); t?.setSelectionRange(t.value.length, t.value.length); }
  if (kind === "new-thread") { ui.apart[id] = true; render(); }
  if (kind === "slide") { ui.slide[b.dataset.run] = Math.max(0, Number(b.dataset.to)); render(); }
  if (kind === "copy") navigator.clipboard?.writeText(b.dataset.text).then(() => toast("Copied."), () => toast("Couldn't copy. Select the text instead.", true));
  if (kind === "rate") act(async () => { await api(`runs/${id}/outcome`, "POST", { success: b.dataset.ok === "true", comment: b.dataset.ok === "true" ? "Manager rated the result good." : "Manager rated the result poor." }); return "Thanks. That counts toward the leaderboard."; }, b);
  if (kind === "cancel") act(async () => { await api(`runs/${id}/cancel`, "POST", {}); return "Task cancelled."; }, b);
  if (kind === "activate") act(async () => {
    const a = agentById(id), ids = a.required_capabilities?.map(c => c.id) || a.bindings.map(x => x.capability_id), bindings = [];
    for (const cid of ids) { const conn = capById(cid)?.connection_id || "support-local", v = await api(`capabilities/${cid}/validate`, "POST", { department_id: a.department_id, connection_id: conn }); bindings.push({ capability_id: cid, connection_id: conn, validation_id: v.id }); }
    await api(`agents/${a.id}`, "PATCH", { bindings, expected_spec_version: a.spec_version });
    return "Connections validated. The agent is ready.";
  }, b);
  if (kind === "perf") (async () => { try { const [p, v] = await Promise.all([api(`agents/${id}/performance`), api(`agents/${id}/versions`)]); ui.metrics[id] = { p, v }; render(); $("details.panel.plain")?.setAttribute("open", ""); } catch (err) { toast(err.message, true); } })();
  if (kind === "share-agent") act(async () => { await api("marketplace", "POST", { kind: "agent", source_id: id }); return "Shared in the Library. No connections or trust included."; }, b);
  if (kind === "rank") { ui.rank = b.dataset.rank; render(); }
  if (kind === "board") { ui.board = b.dataset.tab; render(); }
  if (kind === "lib") { ui.lib = b.dataset.tab; render(); }
});

document.addEventListener("submit", e => {
  const f = e.target, kind = f.dataset.form; if (!kind) return; e.preventDefault();
  const d = Object.fromEntries(new FormData(f)), sub = e.submitter;
  if (sub?.name) d[sub.name] = sub.value;
  if (kind === "create-job") act(async () => { await api("work-queue", "POST", d); return "Job added. Assign an owner to begin."; }, sub);
  if (kind === "assign-ticket") act(async () => { await api(`work-queue/${encodeURIComponent(f.dataset.id)}/assign`, "POST", d); return "Assigned. The agent will pause for required approvals."; }, sub);
  if (kind === "review-ticket") act(async () => { await api(`work-queue/${encodeURIComponent(f.dataset.id)}/review`, "POST", { success: d.success === "true", comment: d.comment }); return "Outcome recorded separately from action approvals."; }, sub);
  if (kind === "run") {
    const a = agentById(f.dataset.id), follow = followTarget(a, S.runs.filter(r => r.agent_id === a.id));
    act(async () => {
      const body = { task: d.task, mode: d.mode, max_steps: 8 };
      if (follow && follow.mode === d.mode) body.follow_up_of = follow.id;
      await api(`agents/${a.id}/runs`, "POST", body);
      if (follow && !body.follow_up_of) ui.apart[a.id] = true; else if (!follow) delete ui.apart[a.id];
      ui.drafts[a.id] = ""; setTimeout(() => scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }), 80);
      return null;
    }, sub);
  }
  if (kind === "decide") {
    if (d.decision === "request_revision" && !d.comment.trim()) { toast("Say what should change before sending it back.", true); f.comment.focus(); return; }
    act(async () => { await api(`approvals/${f.dataset.id}/decision`, "POST", d); return { approve: "Approved. The agent continues.", reject: "Rejected. That action will not run.", request_revision: "Sent back. The agent will propose a new action." }[d.decision]; }, sub);
  }
  if (kind === "add-cap") act(async () => {
    const a = agentById(d.target_agent_id), cap = capById(f.dataset.id);
    const chat = await api("recruiter/conversations", "POST", {});
    const r = await api(`recruiter/conversations/${chat.id}/messages`, "POST", { message: `Add ${cap.name} to ${a.name}.`, capability_ids: [cap.id], target_agent_id: a.id, mode: "demo", model_profile_id: a.model_profile_id, department_id: a.department_id, manager_id: a.manager_id });
    wiz = { ...wiz0(), step: 3, chatId: chat.id, proposal: r.proposal, target: a.id, mode: a.model_profile_id, caps: r.proposal.spec.capability_ids }; location.hash = "#/create";
    return null;
  }, sub);
  if (kind === "install") act(async () => { const l = S.marketplace.find(x => x.id === f.dataset.id), r = await api(`marketplace/${f.dataset.id}/install`, "POST", { department_id: defaultDept(), manager_id: d.manager_id }); if (l.kind === "agent") location.hash = "#/agent/" + r.resource.id; return "Installed. Connect it before its first task."; }, sub);
  if (kind === "new-cap") act(async () => {
    const tools = new FormData(f).getAll("tools"); if (!tools.length) throw Error("Choose at least one tool.");
    await api("capabilities", "POST", { name: d.name, description: d.description, tools }); f.reset(); return "Capability added to the Library.";
  }, sub);
});

document.addEventListener("input", e => {
  const t = e.target.dataset?.draft; if (!t) return;
  if (t === "wiz-text") wiz.text = e.target.value;
  if (t === "wiz-name") wiz.name = e.target.value;
  if (t === "run") ui.drafts[e.target.dataset.id] = e.target.value;
});
document.addEventListener("change", e => {
  const t = e.target.dataset?.draft;
  if (t === "wiz-manager") wiz.manager = e.target.value;
  if (t === "wiz-dept") wiz.dept = e.target.value;
});
document.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.target.matches?.("textarea[data-draft='run']")) { e.preventDefault(); e.target.form.requestSubmit(); }
});
$("#identity").addEventListener("change", e => { user = e.target.value; sessionStorage.setItem("dev-user", user); wiz = wiz0(); S.steps = {}; act(async () => `Now using ${userName(user)}'s workspace.`); });
addEventListener("hashchange", async () => { if (route().name === "agent") await loadSteps().catch(() => {}); render(); enter(); scrollTo({ top: 0 }); });

/* Tilt: pointer-driven depth on cards, fine pointers only */
if (matchMedia("(hover: hover) and (pointer: fine)").matches && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
  document.addEventListener("pointermove", e => {
    const t = e.target.closest?.(".tilt"); if (!t) return;
    const r = t.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
    t.style.setProperty("--ry", ((x - 0.5) * 9).toFixed(2) + "deg"); t.style.setProperty("--rx", ((0.5 - y) * 7).toFixed(2) + "deg");
    t.style.setProperty("--gx", (x * 100).toFixed(1) + "%"); t.style.setProperty("--gy", (y * 100).toFixed(1) + "%"); t.style.setProperty("--glare", "1");
  });
  document.addEventListener("pointerout", e => {
    const t = e.target.closest?.(".tilt"); if (!t || t.contains(e.relatedTarget)) return;
    t.style.setProperty("--rx", "0deg"); t.style.setProperty("--ry", "0deg"); t.style.setProperty("--glare", "0");
  });
}

/* ---------- 3D backdrop: a slowly turning wireframe globe on a canvas ---------- */
function startSpace() {
  const cv = $("#space"), ctx = cv.getContext("2d"); if (!ctx) return;
  const still = matchMedia("(prefers-reduced-motion: reduce)");
  const N = 340, pts = [], links = [], stars = [];
  for (let i = 0; i < N; i++) { const y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y), a = i * 2.399963; pts.push([Math.cos(a) * r, y, Math.sin(a) * r]); }
  for (let i = 0; i < N; i++) {
    const near = pts.map((p, j) => [j, (p[0] - pts[i][0]) ** 2 + (p[1] - pts[i][1]) ** 2 + (p[2] - pts[i][2]) ** 2]).sort((a, b) => a[1] - b[1]).slice(1, 4);
    near.forEach(([j]) => { if (i < j || !near.some(() => false)) links.push([i, j]); });
  }
  for (let i = 0; i < 90; i++) stars.push([(Math.random() - 0.5) * 3.4, (Math.random() - 0.5) * 3.4, (Math.random() - 0.5) * 3.4]);
  const ring = (rx, tilt) => Array.from({ length: 120 }, (_, i) => { const a = (i / 120) * Math.PI * 2; return [Math.cos(a) * rx, Math.sin(a) * rx * Math.sin(tilt), Math.sin(a) * rx * Math.cos(tilt)]; });
  const rings = [ring(1.32, 0.5), ring(1.62, -0.35)];
  let W = 0, H = 0, ry = 0, rx = -0.32, tx = 0, ty = 0, cx = 0, cy = 0, last = 0, raf = 0;
  const size = () => { const d = Math.min(devicePixelRatio || 1, 2); W = innerWidth; H = innerHeight; cv.width = W * d; cv.height = H * d; ctx.setTransform(d, 0, 0, d, 0, 0); };
  const proj = (p, R, spin) => {
    const c = Math.cos(ry * spin), s = Math.sin(ry * spin), x1 = p[0] * c + p[2] * s, z1 = -p[0] * s + p[2] * c, cxr = Math.cos(rx), sxr = Math.sin(rx), y2 = p[1] * cxr - z1 * sxr, z2 = p[1] * sxr + z1 * cxr, k = 1 / (1 - z2 * 0.3);
    return [cxx + x1 * R * k, cyy + y2 * R * k, z2];
  };
  let cxx = 0, cyy = 0;
  function draw() {
    ctx.clearRect(0, 0, W, H);
    const R = Math.min(W, H) * (W < 700 ? 0.5 : 0.4); cxx = W < 700 ? W * 0.5 : W * 0.74; cyy = H * 0.5;
    ctx.fillStyle = "rgba(170,200,255,.35)";
    for (const s of stars) { const [x, y, z] = proj(s, R, 0.35); ctx.globalAlpha = 0.18 + 0.3 * ((z + 1.7) / 3.4); ctx.fillRect(x, y, 1.2, 1.2); }
    ctx.globalAlpha = 1;
    const P = pts.map(p => proj(p, R, 1));
    ctx.lineWidth = 0.7;
    for (const [i, j] of links) { const d = (P[i][2] + P[j][2]) / 2; ctx.strokeStyle = `rgba(79,240,200,${(0.03 + 0.12 * (d + 1) / 2).toFixed(3)})`; ctx.beginPath(); ctx.moveTo(P[i][0], P[i][1]); ctx.lineTo(P[j][0], P[j][1]); ctx.stroke(); }
    for (let i = 0; i < N; i++) { const [x, y, z] = P[i], d = (z + 1) / 2; ctx.fillStyle = `rgba(150,255,226,${(0.08 + 0.55 * d).toFixed(3)})`; ctx.beginPath(); ctx.arc(x, y, 0.7 + 1.5 * d, 0, 6.2832); ctx.fill(); if (i % 41 === 0) { ctx.fillStyle = `rgba(79,240,200,${(0.06 + 0.1 * d).toFixed(3)})`; ctx.beginPath(); ctx.arc(x, y, 7 + 5 * d, 0, 6.2832); ctx.fill(); } }
    ctx.lineWidth = 1;
    rings.forEach((rg, k) => { ctx.strokeStyle = k ? "rgba(143,180,255,.2)" : "rgba(79,240,200,.22)"; ctx.beginPath(); rg.forEach((p, i) => { const [x, y] = proj(p, R, k ? -0.6 : 0.5); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.closePath(); ctx.stroke(); });
  }
  function frame(t) {
    const dt = Math.min(60, t - last || 16); last = t;
    ry += dt * 0.00007; cx += (tx - cx) * 0.04; cy += (ty - cy) * 0.04; rx = -0.32 + cy; ry += (cx - 0) * 0.0004;
    draw(); raf = requestAnimationFrame(frame);
  }
  const start = () => { cancelAnimationFrame(raf); size(); if (still.matches) draw(); else raf = requestAnimationFrame(frame); };
  addEventListener("resize", start);
  addEventListener("pointermove", e => { tx = (e.clientX / innerWidth - 0.5) * 2; ty = (e.clientY / innerHeight - 0.5) * 0.25; }, { passive: true });
  document.addEventListener("visibilitychange", () => { cancelAnimationFrame(raf); if (!document.hidden) start(); });
  still.addEventListener?.("change", start);
  start();
}

/* ---------- boot and polling ---------- */
(async () => {
  startSpace();
  try { await load(); render(); enter(); }
  catch (e) { $("#view").innerHTML = `<div class="panel">${emptyState("Workspace unavailable", "Start the server with python server.py, then reload.")}</div>`; toast(e.message, true); }
})();

(function poll() {
  const active = S.runs?.some(r => !TERMINAL.includes(r.status));
  setTimeout(async () => {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    if (!busy && !document.hidden && ["work", "agents", "inbox", "agent", "leaderboard"].includes(route().name) && !typing) {
      try { const before = JSON.stringify([S.runs, S.approvals, S.agents, S.leaderboard, S["work-queue"], Object.keys(S.steps).length]); await load(); if (before !== JSON.stringify([S.runs, S.approvals, S.agents, S.leaderboard, S["work-queue"], Object.keys(S.steps).length])) { const open = $$("details[open]").map(d => d.querySelector("summary")?.textContent); render(); $$("details").forEach(d => { if (open.includes(d.querySelector("summary")?.textContent)) d.setAttribute("open", ""); }); } } catch { /* retry next tick */ }
    }
    poll();
  }, active ? 1500 : 4000);
})();
