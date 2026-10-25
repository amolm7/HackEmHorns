"use strict";
/* ORBIT: frontend. Talks only to the documented /api endpoints.
   Strict CSP: no inline handlers or styles. Events are delegated; dynamic sizing goes through CSSOM or SVG attributes. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = x => String(x ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const json = x => esc(JSON.stringify(x, null, 2));
const pct = x => (x == null ? "--" : Math.round(x * 100) + "%");
const TERMINAL = ["completed", "failed", "cancelled"];
const clock = iso => { const d = new Date(iso); return isNaN(d) ? "" : d.toTimeString().slice(0, 5); };
const since = (a, b) => { const s = (new Date(b) - new Date(a)) / 1000; return isNaN(s) ? "" : s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m${String(Math.round(s % 60)).padStart(2, "0")}s`; };
/* Headline words blur into place, one after another. */
const words = (text, cls = "") => `<span class="reveal ${cls}">${String(text).split(/(\s+)/).filter(Boolean).map((w, i) => /^\s+$/.test(w) ? " " : `<span class="w d${Math.min(i >> 1, 11)}">${esc(w)}</span>`).join("")}</span>`;

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
  chev: ["M6 9l6 6 6-6"],
  check: ["M5 12.5l4.5 4.5L19 7"],
  x: ["M6 6l12 12", "M18 6L6 18"],
  up: ["M7 11v9H4v-9z", "M7 11l4-7c1.5 0 2.5 1 2.5 2.5V9h5a2 2 0 0 1 2 2.3l-1 6a2 2 0 0 1-2 1.7H7"],
  down: ["M17 13V4h3v9z", "M17 13l-4 7c-1.5 0-2.5-1-2.5-2.5V15h-5a2 2 0 0 1-2-2.3l1-6A2 2 0 0 1 6.5 5H17"],
  back: ["M15 6l-6 6 6 6"],
  next: ["M9 6l6 6-6 6"],
  send: ["M12 19V5", "M6 11l6-6 6 6"],
  inbox: ["M4 13l2-8h12l2 8", "M4 13v6h16v-6", "M4 13h4l1 2h6l1-2h4"],
  trophy: ["M8 4h8v5a4 4 0 0 1-8 0z", "M8 6H5a3 3 0 0 0 3 4", "M16 6h3a3 3 0 0 1-3 4", "M12 13v4", "M8 20h8"],
  library: ["M4 4h5v16H4z", "M11 4h5v16h-5z", "M18 6l3 .8-3.5 13.2-3-.8z"],
  jobs: ["M4 7h16v12H4z", "M9 7V5h6v2", "M4 12h16"],
  more: ["M6 12h.01", "M12 12h.01", "M18 12h.01"],
  calendar: ["M4 6h16v14H4z", "M4 10h16", "M8 3v4", "M16 3v4"],
  mail: ["M3 6h18v12H3z", "M3 7l9 6 9-6"],
  tasks: ["M5 6l1.5 1.5L9 5", "M12 6.5h8", "M5 12l1.5 1.5L9 11", "M12 12.5h8", "M5 18l1.5 1.5L9 17", "M12 18.5h8"],
  download: ["M12 4v11", "M7 11l5 5 5-5", "M5 20h14"],
  spark: ["M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"],
  attach: ["M20 11l-8.5 8.5a5 5 0 0 1-7-7L13 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L14 7"],
  out: ["M7 17L17 7", "M8 7h9v9"],
  files: ["M4 5h6l2 2h8v12H4z"],
};
const icon = (name, cls = "") => `<svg class="ic ${cls}" viewBox="0 0 24 24" aria-hidden="true">${(ICONS[name] || ICONS.tool).map(d => `<path d="${d}"/>`).join("")}</svg>`;

/* ---------- state ---------- */
let csrfToken = null, authMode = "development", authReady = false;
let user = sessionStorage.getItem("dev-user") || "pavan";
let S = { steps: {}, conversations: {} };
let busy = false;
const forge0 = () => ({ caps: [], text: "", name: "", mode: null, more: false, target: "", autoName: false });
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const coarse = () => typeof matchMedia === "function" && matchMedia("(pointer:coarse)").matches;
let forge = forge0();
const ui = { slide: {}, board: "agents", rank: "results", lib: "capabilities", fresh: null, drafts: {}, repositories: {}, newTool: {source: null, name: "", description: "", department: null}, metrics: {}, revise: {}, pulse: 0, stick: true, caption: null, dragFrom: null, files: null, allPeople: false };

class ApiError extends Error {
  constructor(message, info = {}) { super(message); this.name = "ApiError"; Object.assign(this, info); }
}
const errText = e => e?.code === "internal_error" && e.requestId ? `${e.message} (support ID ${String(e.requestId).slice(0, 8)})` : e?.message || "Something went wrong.";
const API_WAIT = { GET: 30000, POST: 110000 };

async function api(path, method = "GET", body) {
  const headers = authMode === "password" ? (csrfToken ? { "X-CSRF-Token": csrfToken } : {}) : { "X-Dev-User": user };
  let replayKey = null;
  if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify([method, path, body])));
    replayKey = "pending-request:" + user + ":" + Array.from(new Uint8Array(bytes), b=>b.toString(16).padStart(2,"0")).join("");
    headers["Idempotency-Key"] = sessionStorage.getItem(replayKey) || crypto.randomUUID();
    sessionStorage.setItem(replayKey, headers["Idempotency-Key"]);
  }
  // Never wait forever: a stalled server must not leave the whole page stuck on "Working…".
  const guard = new AbortController(), timer = setTimeout(() => guard.abort(), API_WAIT[method] || API_WAIT.POST);
  let res;
  try {
    res = await fetch("/api/" + path, { method, headers, signal: guard.signal, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  } catch (e) {
    throw new ApiError(e.name === "AbortError"
      ? "The server took too long to answer. It may still finish, so check the agent before trying again."
      : "Couldn't reach the server. Check that it is running.", { code: e.name === "AbortError" ? "client_timeout" : "network" });
  } finally { clearTimeout(timer); }
  if (replayKey && res.status < 500) sessionStorage.removeItem(replayKey);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(data.error?.message || `Request failed (${res.status}).`,
    { status: res.status, code: data.error?.code, details: data.error?.details, requestId: res.headers.get("X-Request-ID") });
  return data;
}

async function load() {
  const paths = ["me", "dev/users", "departments", "capabilities", "model-profiles", "agents", "marketplace", "leaderboard", "integrations/github"];
  const vals = await Promise.all(paths.map(p => api(p)));
  S = { ...S, ...Object.fromEntries(paths.map((p, i) => [p, vals[i]])) };
  if (authMode === "password") { user = S.me.id; $("#identity").disabled = true; if (!$("#sign-out")) { const b = document.createElement("button"); b.id = "sign-out"; b.className = "btn small"; b.textContent = "Sign out"; b.setAttribute("aria-label", "Sign out"); b.addEventListener("click", async () => { await api("auth/logout", "POST", {}); location.reload(); }); $("#identity").closest("label").after(b); } }
  S.employees = S.me.roles.some(r => ["manager", "admin"].includes(r)) ? await api("employees") : null;
  S.policy = await api("policy").catch(() => ({ approval_scope: "agent" }));
  S.approvals = await api("approvals").catch(() => []);
  S.proposals = await api("recruiter/proposals").catch(() => []);
  if (route().name === "agent" && UUID.test(route().id || "")) { try { await loadSteps(); } catch { S.runs = await api("runs"); } }
  else S.runs = await api("runs");
  sidebar();
  syncActivityStream();
}
function applyActivity(snapshot) {
  const id = snapshot.agent.id;
  const exists = S.agents.some(a => a.id === id);
  S.agents = S.agents.map(a => a.id === id ? snapshot.agent : a).filter(a => a.status !== "archived");
  if (!exists && snapshot.agent.status !== "archived") S.agents.push(snapshot.agent);
  S.runs = [...(S.runs || []).filter(r => r.agent_id !== id), ...snapshot.runs];
  S.approvals = [...(S.approvals || []).filter(a => a.agent_id !== id), ...snapshot.approvals];
  S.conversations[id] = snapshot.conversations;
  for (const run of snapshot.runs) S.steps[run.id] = { updated: run.updated_at, list: snapshot.steps.filter(x => x.run_id === run.id) };
}
async function loadSteps() {
  const r = route();
  if (r.name === "agent" && UUID.test(r.id || "")) applyActivity(await api(`agents/${r.id}/activity`));
}

/* One authenticated status stream for the open chat; no model-token streaming. */
let activityConnection = null;
function syncActivityStream() {
  const id = route().name === "agent" && UUID.test(route().id || "") && !document.hidden ? route().id : null;
  const key = id ? user + ":" + id : null;
  if (activityConnection?.key === key) return;
  activityConnection?.controller.abort();
  activityConnection = null;
  if (!key) return;
  const state = { key, controller: new AbortController() };
  activityConnection = state;
  (async () => {
    while (!state.controller.signal.aborted) {
      try {
        const response = await fetch(`/api/agents/${id}/events`, { headers: authMode === "password" ? {} : { "X-Dev-User": user }, signal: state.controller.signal });
        if (!response.ok || !response.body) throw Error("Activity stream unavailable");
        const reader = response.body.getReader(), decoder = new TextDecoder();
        let buffer = "";
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let end;
            while ((end = buffer.indexOf("\n\n")) >= 0) {
              const block = buffer.slice(0, end); buffer = buffer.slice(end + 2);
              if (block.startsWith("event: access-lost")) { state.controller.abort(); toast("Agent access changed. Refresh your workspace.", true); break; }
              if (!block.startsWith("event: snapshot") || activityConnection !== state) continue;
              const line = block.split("\n").find(x => x.startsWith("data: "));
              if (line) { applyActivity(JSON.parse(line.slice(6))); ui.activityDirty = true; flushActivity(); }
            }
          }
        } finally { reader.releaseLock(); }
      } catch (e) { if (state.controller.signal.aborted) return; }
      if (!state.controller.signal.aborted) await new Promise(resolve => setTimeout(resolve, 2500));
    }
  })();
}
function flushActivity() {
  if (!ui.activityDirty || busy || document.hidden || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) || $("details.menu[open]")) return;
  ui.activityDirty = false;
  const open = $$("details.quiet[open]").map(d => d.querySelector("summary")?.textContent);
  ui.stick = innerHeight + scrollY > document.body.scrollHeight - 200;
  sidebar(); render(); ui.stick = true;
  $$("details.quiet").forEach(d => { if (open.includes(d.querySelector("summary")?.textContent)) d.setAttribute("open", ""); });
}
document.addEventListener("focusout", () => setTimeout(flushActivity, 0));
document.addEventListener("visibilitychange", syncActivityStream);

/* ---------- lookups ---------- */
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
/* "agent": a manager approves each agent once, when it is created; its tasks then run without per-action review. */
const perAction = () => S.policy?.approval_scope === "action";
const canRemove = a => !!a && (canManage(a) || a.creator_id === user);
const abilities = a => capsOf(a).map(c => c.name.toLowerCase());
const defaultDept = () => S.me.department_ids[0] || "support";
const defaultManager = () => isManager() ? user : (S.me.manager_id || S["dev/users"].find(u => u.roles.includes("manager") && u.department_ids.includes(defaultDept()))?.id);
const capsOf = a => (a.bindings.length ? a.bindings.map(b => b.capability_id) : (a.required_capabilities || []).map(c => c.id)).map(id => capById(id)).filter(Boolean);
const TOOL_VERB = { create_slideshow: "build a slideshow", create_document: "write a document", analyze_data: "analyze your data", read_url: "read a web page", search_tickets: "search support tickets", search_docs: "search help documents", create_draft: "save a reply draft", schedule_meeting: "schedule a meeting", draft_email: "draft an email", create_task_list: "make a task list" };
Object.assign(TOOL_VERB, { github_read_file: "read repository files", github_list_issues: "read repository issues" });
const RISK_ACTION = { read: "reads only", local_write: "saves in your workspace", always_approve: "always asks" };
const RISK_AGENT = { read: "reads only", local_write: "saves in your workspace", always_approve: "saves a draft, never sends" };
const RISK = new Proxy({}, { get: (_, k) => (perAction() ? RISK_ACTION : RISK_AGENT)[k] });
const SHORT = { "make-slideshow": "Slides", "write-document": "Documents", "analyze-data": "Data", "research-web": "Web research", "ticket-search": "Tickets", "help-docs": "Help docs", "reply-drafts": "Reply drafts", "schedule-meetings": "Meetings", "draft-email": "Email", "plan-tasks": "Tasks" };
const short = c => SHORT[c.id] || c.name;
const usesGitHub = a => capsOf(a).some(c => c.tools?.some(t => t.startsWith("github_")));
const opts = (list, sel) => list.map(([v, t, dis]) => `<option value="${esc(v)}" ${v === sel ? "selected" : ""} ${dis ? "disabled" : ""}>${esc(t)}</option>`).join("");
const agentState = a => S.runs.some(r => r.agent_id === a.id && r.status === "awaiting_approval") ? "waiting" : S.runs.some(r => r.agent_id === a.id && ["queued", "running"].includes(r.status)) ? "working" : a.status !== "active" ? "setup" : "";

function hash(str) { let h = 2166136261; for (const c of String(str)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
/* Each agent is a small glowing orb with an orbit ring: dashed while it asks first, lit when it runs alone. */
function orb(id, { size = 40, level = "intern", cls = "" } = {}) {
  const h = hash(id), hue = [188, 200, 214, 228, 172, 244][h % 6], gid = "o" + h + "-" + size, on = level !== "intern";
  return `<svg class="orb ${on ? "alone" : ""} ${cls}" viewBox="-20 -20 40 40" width="${size}" height="${size}" aria-hidden="true"><defs><radialGradient id="${gid}" cx="36%" cy="30%" r="80%"><stop offset="0" stop-color="hsl(${hue} 100% 95%)"/><stop offset=".45" stop-color="hsl(${hue} 85% 66%)"/><stop offset="1" stop-color="hsl(${(hue + 40) % 360} 70% 22%)"/></radialGradient></defs><circle class="core" r="10" fill="url(#${gid})"/><ellipse class="ring" rx="17.5" ry="6.4" fill="none" stroke="${on ? "#bfefff" : "#8ea2d8"}" stroke-opacity="${on ? 0.95 : 0.55}" stroke-width="1.2" ${on ? "" : 'stroke-dasharray="3 3"'} transform="rotate(${-26 + (h % 5) * 6})"/></svg>`;
}

let toastTimer;
function toast(msg, error = false) {
  const t = $("#toast"); t.textContent = msg; t.classList.toggle("error", error); t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, error ? 7000 : 3400);
}
async function act(fn, el) {
  if (busy) return;
  busy = true;
  const original = el?.innerHTML;
  if (el?.tagName === "BUTTON" && !el.classList.contains("icon-only") && !el.classList.contains("send")) el.textContent = "Working…";
  el?.setAttribute("aria-busy", "true");
  const btns = el ? $$("button", el.closest("form") || el.parentElement || el).filter(b => !b.disabled) : [];
  btns.forEach(b => { b.disabled = true; });
  try { const msg = await fn(); await load(); render(); if (msg) toast(msg); }
  catch (e) { await load().catch(() => {}); render(); toast(errText(e), true); }
  finally { busy = false; if (el?.isConnected && original !== undefined) { el.innerHTML = original; el.removeAttribute("aria-busy"); } btns.forEach(b => { if (b.isConnected) b.disabled = false; }); }
}

/* ---------- routing ---------- */
function route() {
  const [raw, id] = location.hash.replace(/^#\/?/, "").split("/");
  const alias = { create: "new", hire: "new", work: "new", home: "new", agents: "new", arcade: "new", queue: "inbox", approvals: "inbox", scores: "leaderboard", shop: "library" };
  return { name: alias[raw] || raw || "new", id };
}
const TITLES = { new: "New agent", inbox: "Approvals", files: "Files", leaderboard: "Leaderboard", library: "Library", employees: "Employees" };
function render() {
  const r = route();
  const views = { new: forgeScreen, agent: chatScreen, inbox: inboxScreen, files: filesScreen, leaderboard: leaderboardScreen, library: libraryScreen, employees: employeesScreen };
  document.body.dataset.view = r.name;
  $("#view").innerHTML = (views[r.name] || forgeScreen)(r.id);
  document.title = (r.name === "agent" ? agentById(r.id)?.name || "Agent" : TITLES[r.name] || "New agent") + " · ORBIT";
  sidebarActive();
  if (r.name === "agent" && ui.stick) requestAnimationFrame(() => scrollTo({ top: document.body.scrollHeight }));
  if (ui.fresh) setTimeout(() => { ui.fresh = null; }, 1400);
}
function enter() { const v = $("#view"); v.classList.remove("enter"); void v.offsetWidth; v.classList.add("enter"); setTimeout(() => v.classList.remove("enter"), 1600); }

/* ---------- sidebar: agents are the navigation, like conversations ---------- */
const sidebarMarkup = new Map();
function stableSidebar(selector, markup) {
  if (sidebarMarkup.get(selector) !== markup) {
    $(selector).innerHTML = markup;
    sidebarMarkup.set(selector, markup);
  }
}
function agentMenu(a) {
  const manages = canManage(a);
  return `<details class="menu agent-menu"><summary aria-label="Options for ${esc(a.name)}" title="Agent options">${icon("more")}</summary><div class="menu-pop">
          ${manages ? `<button data-act="teach" data-id="${esc(a.id)}">Add a tool</button><button data-act="rename" data-id="${esc(a.id)}">Rename</button>` : ""}
          ${manages ? `<button data-act="share-agent" data-id="${esc(a.id)}">Share as template</button>` : ""}
          ${a.status === "active" ? `<button data-act="new-thread" data-id="${esc(a.id)}">New conversation</button>` : ""}
          <button data-act="perf" data-id="${esc(a.id)}">About this agent</button>
          ${canRemove(a) ? `<button class="danger" data-act="archive" data-id="${esc(a.id)}">Delete agent</button>` : ""}</div></details>`;
}
function sidebar() {
  stableSidebar("#identity", opts(S["dev/users"].map(u => [u.id, `${u.name} · ${u.roles.join(", ")}`]), user));
  stableSidebar("#identity-menu", dropdown({ field: "identity", value: user, label: authMode === "password" ? "Signed in account" : "Switch identity", cls: "up" + (authMode === "password" ? " locked" : ""), options: S["dev/users"].map(u => [u.id, `${u.name} · ${u.roles.join(", ")}`]) }));
  const pending = S.approvals.filter(a => a.status === "pending").length + S.proposals.filter(p => p.status === "draft").length;
  // Starting a conversation moves its agent to the top; background completions
  // do not displace the agent the user most recently worked with.
  const lastUsed = new Map();
  for (const run of S.runs || []) {
    const timestamp = Date.parse(run.created_at) || 0;
    lastUsed.set(run.agent_id, Math.max(lastUsed.get(run.agent_id) || 0, timestamp));
  }
  const recentAgents = [...S.agents].sort((a, b) =>
    (lastUsed.get(b.id) || Date.parse(b.created_at) || 0) -
    (lastUsed.get(a.id) || Date.parse(a.created_at) || 0)
  );
  const agentRow = a => { const st = agentState(a); return `<li class="agent-nav-row"><a href="#/agent/${esc(a.id)}" data-id="${esc(a.id)}">${orb(a.id, { size: 24, level: a.level })}<span class="nm">${esc(a.name)}</span>${st ? `<span class="st ${st}" title="${st === "waiting" ? "Needs your approval" : st === "working" ? "Working" : "Needs setup"}"></span>` : ""}</a>${agentMenu(a)}</li>`; };
  let agentList;
  if (S.me.roles.some(r => ["manager", "admin"].includes(r))) {
    const creators = new Map();
    for (const agent of recentAgents) {
      const owner = agent.creator_id || "unknown";
      if (!creators.has(owner)) creators.set(owner, []);
      creators.get(owner).push(agent);
    }
    const group = (owner, agents, mine = false) => `<li class="agent-owner-group"><h3 class="agent-owner-label">${mine ? "My agents" : esc(owner === "unknown" ? "Unknown creator" : userName(owner))}<span>${agents.length}</span></h3><ul class="agent-owner-list">${agents.map(agentRow).join("") || '<li class="none">No agents created yet</li>'}</ul></li>`;
    agentList = group(user, creators.get(user) || [], true);
    creators.delete(user);
    if (creators.size) agentList += '<li class="agent-team-heading">Team agents · by creator</li>';
    // Groups follow their most recent agent; agents within each group remain recent-first.
    agentList += [...creators].map(([owner, agents]) => group(owner, agents)).join("");
  } else {
    agentList = recentAgents.map(agentRow).join("") || '<li class="none">No agents yet</li>';
  }
  stableSidebar("#agent-list", agentList);
  const managerNav = $("#manager-nav");
  managerNav.hidden = !S.me.roles.some(r => ["manager", "admin"].includes(r));
  stableSidebar("#manager-nav", managerNav.hidden ? "" : `<a class="employees-nav" href="#/employees" data-route="employees">${icon("jobs")}<span><b>Employees</b><small>Team overview & usage</small></span>${icon("out", "sm")}</a>`);
  stableSidebar("#side-links", [["inbox", "inbox", "Approvals", pending], ["files", "files", "Files", 0], ["leaderboard", "trophy", "Leaderboard", 0], ["library", "library", "Library", 0]].map(([r, ic, t, n]) => `<li><a href="#/${r}" data-route="${r}">${icon(ic)}<span class="nm">${t}</span>${n ? `<span class="count ${r === "inbox" ? "warn" : ""}">${n}</span>` : ""}</a></li>`).join(""));
  sidebarActive();
}
function sidebarActive() {
  const r = route();
  $$("#agent-list a").forEach(a => a.toggleAttribute("aria-current", r.name === "agent" && a.dataset.id === r.id));
  $$("#side-links a, #manager-nav a").forEach(a => a.toggleAttribute("aria-current", a.dataset.route === r.name));
  $("#new-agent")?.toggleAttribute("aria-current", r.name === "new");
}

/* ---------- creator: drag tools onto the core, say what it should do ---------- */
const EXAMPLES = { "make-slideshow": "Turn my meeting notes into a 5-slide deck", "write-document": "Write a one-page brief from a few bullet points", "analyze-data": "Find what stands out in a CSV I paste", "research-web": "Summarize the web pages I send it", "schedule-meetings": "Set up a 30-minute kickoff with sam@acme.com next Tuesday at 2pm", "draft-email": "Draft a polite email asking for the signed contract by Friday", "plan-tasks": "Turn my meeting notes into action items with owners" };
/* In-page dropdown (replaces the native, OS-drawn <select> popup). */
const dropdown = ({ field, value, options, label, cls = "" }) => {
  const cur = options.find(o => o[0] === value) || options[0] || ["", ""];
  return `<details class="menu dd ${cls}" data-dd="${esc(field)}"><summary aria-label="${esc(label)}" aria-haspopup="listbox"><span>${esc(cur[1])}</span>${icon("chev", "sm")}</summary><div class="menu-pop dd-pop" role="listbox" aria-label="${esc(label)}">${options.map(([v, t, off]) => `<button type="button" role="option" aria-selected="${v === value}" data-act="pick" data-field="${esc(field)}" data-value="${esc(v)}" ${off ? "disabled" : ""}><span>${esc(t)}</span>${v === value ? icon("check", "sm") : ""}</button>`).join("")}</div></details>`;
};

/* Starter instructions: each fills the Instructions box, names the agent and picks its tools. */
const ROLES = [
  { id: "atlas", name: "Atlas", title: "Executive Strategist", caps: ["make-slideshow"], text: "Create slides for executives making a decision. Lead with a recommendation, then show supporting evidence, business impact, risks, and next steps. Keep slides concise. Use only supplied facts and label assumptions." },
  { id: "spark", name: "Spark", title: "Storytelling Coach", caps: ["make-slideshow"], text: "Create slides for an audience learning about a topic. Build a story: problem, why it matters, explanation, example, and takeaway. Use approachable language, visual comparisons, and memorable headlines. Use only supplied facts and label assumptions." },
  { id: "quill", name: "Quill", title: "Brief Writer", caps: ["write-document"], text: "Write one-page briefs for busy readers. Start with the bottom line, then key points, what is still unknown, and recommended next steps. Plain language, short paragraphs. Use only supplied facts and label assumptions." },
  { id: "lens", name: "Lens", title: "Data Analyst", caps: ["analyze-data"], text: "Analyze the data I send. Compare groups, point out what stands out, and say what the data cannot tell us. Never claim causes or ROI the data does not show. Finish with two or three plain-language takeaways." },
  { id: "cadence", name: "Cadence", title: "Meeting Coordinator", caps: ["schedule-meetings"], text: "Set up meetings from short requests. Confirm the title, time, length and attendees, add a short agenda, and prepare the calendar invite. Never send invites yourself. Ask one question if a time or person is missing." },
  { id: "relay", name: "Relay", title: "Email Drafter", caps: ["draft-email"], text: "Draft clear, polite emails from a few notes. Keep them short, put the ask in the first two sentences, and match the tone I describe. Save every email as a draft. Never claim an email was sent." },
  { id: "anchor", name: "Anchor", title: "Action Planner", caps: ["plan-tasks"], text: "Turn meeting notes and plans into action items. Give every task an owner and a due date when the notes mention them, and mark anything unclear as to be confirmed. Keep each task to one line." },
];
const roleChips = picked => { const ids = picked.map(c => c.id), fits = r => r.caps.some(c => ids.includes(c)); return [...ROLES.filter(fits), ...ROLES.filter(r => !fits(r))].slice(0, 4); };
const nameTaken = name => S.agents.some(a => a.name.trim().toLowerCase() === String(name).trim().toLowerCase());
const uniqueName = base => { if (!nameTaken(base)) return base; for (let n = 2; ; n++) if (!nameTaken(`${base} ${n}`)) return `${base} ${n}`; };
const isGithubCap = c => !!c?.tools?.some(t => t.startsWith("github_"));
/* One place decides whether Create is allowed, and says why not in plain words. */
function createState() {
  const target = forge.target && agentById(forge.target);
  const picked = forge.caps.map(capById).filter(Boolean);
  const needsLive = picked.some(isGithubCap);
  const blocked = needsLive && (target ? (profile(target.model_profile_id)?.id || "demo") === "demo" : forge.mode === "demo");
  let why = "";
  if (!canHire()) why = "Your role can't create agents.";
  else if (blocked) why = "GitHub needs a live model.";
  else if (target) why = forge.caps.length ? "" : "Pick a tool to add.";
  else if (!forge.name.trim()) why = "Name your agent to continue.";
  else if (nameTaken(forge.name)) why = `An agent called ${forge.name.trim()} already exists. Pick another name.`;
  else if (!forge.caps.length && !forge.text.trim()) why = "Add a tool or write instructions.";
  return { target, picked, needsLive, blocked, why, ok: !why };
}
function syncCreate() {
  const go = $("[data-act='create']"); if (!go) return;
  const s = createState(); go.disabled = !s.ok;
  const why = $("#create-why"); if (why) why.textContent = s.why;
  $$(".starter").forEach(b => b.setAttribute("aria-pressed", String(ROLES.find(r => r.id === b.dataset.id)?.text === forge.text)));
}
const toolCaption = () => { const c = ui.caption && capById(ui.caption); return c ? `${short(c)}: ${c.description}` : coarse() ? "Tap a tool to add it. Tap it on the core to remove it." : "Drag a tool onto the core, or press Enter on it. Drag it back down to remove it."; };
function forgeScreen() {
  if (!forge.mode) forge.mode = S["model-profiles"].find(m => m.id !== "demo" && m.enabled)?.id || "demo";
  const work = S.capabilities.filter(c => (c.group || "Workspace") !== "Support sandbox"), extra = S.capabilities.filter(c => c.group === "Support sandbox");
  const picked = forge.caps.map(capById).filter(Boolean), target = forge.target && agentById(forge.target);
  const free = c => !forge.caps.includes(c.id);
  const tool = c => `<button type="button" class="tool" draggable="true" data-act="tool" data-id="${esc(c.id)}" aria-pressed="false" title="${esc(c.description)}">${icon(c.icon || "tool")}<span>${esc(short(c))}</span></button>`;
  const roles = roleChips(picked);
  const needsLive = picked.some(isGithubCap);
  if (!target && needsLive && forge.mode === "demo") { const live = S["model-profiles"].find(m => m.id !== "demo" && m.enabled); if (live) forge.mode = live.id; }
  const state = createState(), blocked = state.blocked;
  const blockNote = blocked ? `<p class="note warn-note">GitHub reading needs a live model (Meta or Gemini). ${target ? `${esc(target.name)} uses the Demo model, so create a new agent for GitHub.` : "Pick one in the model menu. Demo can't read repositories."}</p>` : "";
  const beltTools = work.filter(free), moreTools = extra.filter(free);
  const belt = beltTools.map(tool).join("") + (forge.more ? moreTools.map(tool).join("") : moreTools.length ? `<button type="button" class="tool ghost" data-act="more-tools" title="Sample support tools: tickets, help documents, reply drafts">${icon("more")}<span>More tools</span></button>` : "");
  return `<div class="forge-screen ${target ? "teach" : ""}">
    <h1 class="display">${words(target ? "Teach " + target.name + " something new" : "Build an agent")}</h1>
    <p class="lede">${target ? (coarse() ? "Tap a new tool to add it." : "Drop a new tool on the core.") : (coarse() ? "Tap the tools it needs to add them to the core. Then write its instructions." : "Drag the tools it needs onto the core. Then write its instructions.")}</p>
    <div class="forge">
      <div class="core-zone ${picked.length ? "armed" : ""} p${ui.pulse % 2}" data-drop="core" aria-label="Tools your agent will have">
        <div class="halo"></div>
        <div class="core">${orb(target ? target.id : "forge", { size: 120, level: picked.length ? "associate" : "intern", cls: "big" })}</div>
        <ul class="orbit n${picked.length}">${picked.map((c, i) => `<li class="slot s${i}"><button type="button" class="tool on" draggable="true" data-from="orbit" data-act="tool" data-id="${esc(c.id)}" aria-label="Remove ${esc(c.name)}" title="Click, or drag back down, to remove">${icon(c.icon || "tool")}<span>${esc(short(c))}</span></button></li>`).join("")}</ul>
        ${picked.length ? "" : `<span class="drop-hint">${coarse() ? "Tap tools to add them" : "Drop tools here"}</span>`}
      </div>
      <div class="belt" data-drop="belt" role="group" aria-label="Tools. Drag onto the core, or click to add.">${belt || `<span class="note">Every tool is on the core.</span>`}</div>
      <p class="tool-caption" id="tool-caption" aria-live="polite">${esc(toolCaption())}</p>
    </div>
    <div class="ask-pane">
    ${target ? `<p class="note">${perAction() ? "Adding tools resets this agent to asks first. Pending tasks must be restarted." : "New tools apply from the next task. Unfinished tasks must be restarted."}</p><div class="ask-row center"><a class="btn ghost" href="#/agent/${esc(target.id)}">Cancel</a><button class="btn primary" data-act="create" ${state.ok ? "" : "disabled"}>Add to ${esc(target.name)}</button></div><p class="why" id="create-why" role="status">${esc(state.why)}</p>${blockNote}` : `<div class="ask-box">
      <textarea id="forge-text" data-draft="forge-text" rows="5" aria-label="Instructions for your agent" placeholder="Describe the job. For example: Create slides for executives making a decision. Lead with a recommendation, then evidence, risks and next steps. Use only the facts I give you.">${esc(forge.text)}</textarea>
      ${coarse() ? "" : `<p class="note kbd" id="forge-tip">Enter adds a line. Press ⌘ or Ctrl + Enter to create.</p>`}
      <div class="starters" role="group" aria-label="Start from an example"><p class="note">Start from an example</p><div class="starter-grid">${roles.map(r => `<button type="button" class="starter" data-act="role" data-id="${esc(r.id)}" aria-pressed="${forge.text === r.text}" title="${esc(r.text)}"><b>${esc(r.name)}</b><span>${esc(r.title)}</span></button>`).join("")}</div></div>
      <div class="ask-row">
        <span class="model-pick" title="Set once. The agent always uses this model.">${dropdown({ field: "forge-mode", value: forge.mode, label: "Model, set once for this agent", options: S["model-profiles"].map(m => [m.id, m.id === "demo" ? "Demo model" : m.name + (m.enabled ? "" : " (needs key)"), !m.enabled]) })}</span>
        <label class="name-field"><span class="sr-only">Agent name (required)</span><input data-draft="forge-name" value="${esc(forge.name)}" placeholder="Name your agent" maxlength="100" required autocomplete="off"></label>
        <button class="btn primary" data-act="create" ${state.ok ? "" : "disabled"}>Create agent</button>
      </div>
      <p class="why" id="create-why" role="status">${esc(state.why)}</p>
    </div>`}
    ${blockNote && !target ? blockNote : ""}
    ${canHire() ? "" : `<p class="note">Your role can't create agents. Switch to a manager or builder at the bottom left.</p>`}
    ${!target ? `<p class="note">The model is set once, here. ${forge.mode === "demo" ? "Demo model runs the real tools on fixed templates, no AI. Add an API key for original writing." : "This agent will always use it."}${!perAction() && !isManager() ? " A manager approves new agents before they can work." : ""}</p>` : ""}
    </div>
  </div>`;
}

/* ---------- chat ---------- */
function parseOutline(text) {
  const slides = []; let cur = null;
  for (const raw of String(text).split("\n")) {
    const line = raw.trim(); if (!line) continue;
    if (line.startsWith("#")) { cur = { title: line.replace(/^#+\s*/, "") || "Untitled", bullets: [] }; slides.push(cur); }
    else { if (!cur) { cur = { title: "Overview", bullets: [] }; slides.push(cur); } cur.bullets.push(line.replace(/^[-*•]\s*/, "")); }
  }
  return slides;
}
function whenText(start, minutes) {
  const d = new Date(start); if (isNaN(d)) return String(start || "");
  const end = new Date(d.getTime() + (Number(minutes) || 30) * 60000);
  const t = x => x.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return `${d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })} · ${t(d)} to ${t(end)}`;
}
/* Everything an agent saves can leave as a plain file. */
const slug = s => String(s || "file").replace(/[^\w -]+/g, "").trim().replace(/\s+/g, "-").toLowerCase() || "file";
function exportOf(r) {
  if (r.kind === "slideshow") return { label: "Download .md", name: slug(r.title) + ".md", mime: "text/markdown", text: `# ${r.title}\n\n` + r.slides.map((x, k) => `## ${k + 1}. ${x.title}\n\n${[x.lead, x.quote && `> ${x.quote.text}${x.quote.by ? " — " + x.quote.by : ""}`, ...(x.stats || []).map(t => `**${t.value}** ${t.label}`), ...x.bullets.map((b, j) => (x.ordered ? `${j + 1}. ` : "- ") + b)].filter(Boolean).join("\n")}${x.notes ? `\n\n_Speaker notes: ${x.notes}_` : ""}`).join("\n\n") };
  if (r.kind === "document") return { label: "Download .md", name: slug(r.title) + ".md", mime: "text/markdown", text: `# ${r.title}\n\n${r.body}` };
  if (r.kind === "email") return { label: "Download .eml", name: slug(r.subject) + ".eml", mime: "message/rfc822", text: `To: ${(r.to || []).join(", ")}\nSubject: ${r.subject}\nX-Unsent: 1\nContent-Type: text/plain; charset=utf-8\n\n${r.body}` };
  if (r.kind === "tasks") return { label: "Download .md", name: slug(r.title) + ".md", mime: "text/markdown", text: `# ${r.title}\n\n` + r.tasks.map(t => `- [ ] ${t.text}${t.owner ? " (" + t.owner + ")" : ""}${t.due ? " by " + t.due : ""}`).join("\n") };
  if (r.kind === "analysis") return { label: "Download .md", name: "analysis.md", mime: "text/markdown", text: "# Analysis\n\n" + (r.highlights || []).map(h => "- " + h).join("\n") + (r.chart ? `\n\n| ${r.chart.x} | ${r.chart.y} |\n| --- | --- |\n` + r.chart.points.map(p => `| ${p.label} | ${p.value} |`).join("\n") : "") };
  return null;
}
const downloadBtn = r => { const e = exportOf(r); return e ? `<button class="link-btn" data-act="download" data-name="${esc(e.name)}" data-mime="${esc(e.mime)}" data-text="${esc(e.text)}">${icon("download", "sm")}${esc(e.label)}</button>` : ""; };
function saveFile(name, mime, text) {
  const url = URL.createObjectURL(new Blob([text], { type: mime + ";charset=utf-8" })), a = document.createElement("a");
  a.href = url; a.download = name; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const playbook = text => `<ul class="playbook">${String(text || "").split("\n").filter(Boolean).map(l => `<li>${esc(l)}</li>`).join("")}</ul>`;
function preview(a) {
  const t = a.action.tool_id, g = a.action.arguments || {};
  let lines = [];
  if (t === "create_slideshow") lines = [`<b>${esc(g.title)}</b>`, ...parseOutline(g.outline).map((x, i) => `${i + 1}. ${esc(x.title)}`)];
  else if (t === "create_document") lines = [`<b>${esc(g.title)}</b>`, ...String(g.body).split("\n").filter(Boolean).slice(0, 5).map(esc)];
  else if (t === "analyze_data") lines = [`${Math.max(0, String(g.table).trim().split("\n").length - 1)} rows of data`, ...(g.question ? [esc(g.question)] : [])];
  else if (t === "read_url") lines = [esc(g.url)];
  else if (t === "schedule_meeting") lines = [`<b>${esc(g.title)}</b>`, esc(whenText(g.start, g.duration_minutes)), ...(g.attendees ? [esc(g.attendees)] : [])];
  else if (t === "draft_email") lines = [`<b>${esc(g.subject)}</b>`, ...(g.to ? ["To " + esc(g.to)] : []), ...String(g.body).split("\n").filter(Boolean).slice(0, 3).map(esc)];
  else if (t === "create_task_list") lines = [`<b>${esc(g.title)}</b>`, ...String(g.tasks).split("\n").filter(Boolean).slice(0, 5).map(x => esc(x.replace(/^[-*•]\s*/, "")))];
  else if (t === "create_draft") lines = [`Ticket ${esc(g.ticket_id)}`, esc(g.body)];
  else lines = [`Search: ${esc(g.query)}`];
  return `<ul class="plan">${lines.map(l => `<li>${l}</li>`).join("")}</ul><details class="quiet"><summary>Exact data</summary><pre>${json(g)}</pre></details>`;
}
function askBlock(a, standalone = false) {
  const ag = agentById(a.agent_id), mine = a.assigned_manager_id === user || S.me.roles.includes("admin"), open = ui.revise[a.id];
  return `<div class="ask ${standalone ? "standalone" : ""}">
    ${standalone ? `<a class="who" href="#/agent/${esc(a.agent_id)}">${orb(a.agent_id, { size: 22, level: ag?.level })}${esc(ag?.name || "Agent")}</a>` : ""}
    <p class="ask-q"><b>${esc(a.action.summary || "Review this proposed action.")}</b> Okay to go ahead?</p>
    ${preview(a)}
    <form class="decide" data-form="decide" data-id="${esc(a.id)}">
      ${open ? `<input name="comment" placeholder="What should change?" aria-label="What should change" required>` : ""}
      <div class="row">${open ? `<button class="btn primary small" name="decision" value="request_revision" ${mine ? "" : "disabled"}>Send back</button><button type="button" class="btn ghost small" data-act="revise" data-id="${esc(a.id)}">Never mind</button>`
        : `<button class="btn primary small" name="decision" value="approve" ${mine ? "" : "disabled"}>Go ahead</button><button type="button" class="btn small" data-act="revise" data-id="${esc(a.id)}" ${mine ? "" : "disabled"}>Change something</button><button class="btn ghost small" name="decision" value="reject" ${mine ? "" : "disabled"}>Don't</button>`}
        ${mine ? "" : `<span class="note">Waiting for ${esc(userName(a.assigned_manager_id))}</span>`}</div>
    </form></div>`;
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
  const n = r.slides.length, i = Math.min(ui.slide[runId] || 0, n - 1), s = r.slides[i], layout = s.layout || (i === 0 && !s.bullets.length ? "cover" : "list");
  const title = layout === "cover" && !s.bullets.length ? r.title : s.title;
  const body = (s.lead ? `<p class="lead">${esc(s.lead)}</p>` : "")
    + (s.stats?.length ? `<div class="stats">${s.stats.map(x => `<div><b>${esc(x.value)}</b><span>${esc(x.label)}</span></div>`).join("")}</div>` : "")
    + (s.quote ? `<blockquote><p>${esc(s.quote.text)}</p>${s.quote.by ? `<cite>${esc(s.quote.by)}</cite>` : ""}</blockquote>` : "")
    + (s.bullets.length ? (s.ordered ? `<ol class="steps">${s.bullets.map(b => `<li>${esc(b)}</li>`).join("")}</ol>` : `<ul>${s.bullets.map(b => `<li>${esc(b)}</li>`).join("")}</ul>`) : "");
  return `<figure class="slides"><div class="stage t-${esc(r.theme || "aurora")} l-${esc(layout)}" tabindex="0" role="group" aria-roledescription="slide" aria-label="Slide ${i + 1} of ${n}. Use the arrow keys to move." data-run="${esc(runId)}" data-n="${n}"><h3>${esc(title)}</h3>${body}<span class="num">${i + 1} / ${n}</span>
      <button class="nav prev" data-act="slide" data-run="${esc(runId)}" data-to="${i - 1}" ${i === 0 ? "disabled" : ""} aria-label="Previous slide">${icon("back")}</button><button class="nav next" data-act="slide" data-run="${esc(runId)}" data-to="${i + 1}" ${i === n - 1 ? "disabled" : ""} aria-label="Next slide">${icon("next")}</button></div>
    <figcaption><span class="dots-nav">${r.slides.map((x, k) => `<button data-act="slide" data-run="${esc(runId)}" data-to="${k}" aria-current="${k === i}" aria-label="Slide ${k + 1}: ${esc(x.title)}"></button>`).join("")}</span><span class="note">${esc(r.title)} · saved in your workspace</span>${downloadBtn(r)}<button class="link-btn" data-act="copy" data-text="${esc(`${r.title}\n\n` + r.slides.map((x, k) => `${k + 1}. ${x.title}\n${[x.lead, x.quote && `“${x.quote.text}”${x.quote.by ? " — " + x.quote.by : ""}`, ...(x.stats || []).map(t => t.value + " " + t.label), ...x.bullets.map((b, j) => x.ordered ? `${j + 1}. ${b}` : b)].filter(Boolean).map(b => "  - " + b).join("\n")}${x.notes ? "\n  Notes: " + x.notes : ""}`).join("\n\n"))}">Copy text</button></figcaption>
    ${s.notes ? `<details class="quiet"><summary>Speaker notes</summary><p class="note">${esc(s.notes)}</p></details>` : ""}</figure>`;
}
function chartSvg(c) {
  const pts = c.points; if (!pts.length) return "";
  const W = 520, H = 220, L = 10, B = 30, T = 22, max = Math.max(...pts.map(p => p.value), 1), bw = (W - L * 2) / pts.length, top = pts.reduce((m, p) => (p.value > m.value ? p : m), pts[0]);
  const bars = pts.map((p, i) => { const h = Math.max(2, (p.value / max) * (H - B - T)), x = L + i * bw + bw * 0.22, w = bw * 0.56, y = H - B - h; return `<rect class="bar ${p === top ? "" : "dim"}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" rx="4"/><text class="val" x="${(x + w / 2).toFixed(1)}" y="${(y - 7).toFixed(1)}" text-anchor="middle">${esc(p.value.toLocaleString(undefined, { maximumFractionDigits: 1 }))}</text><text x="${(x + w / 2).toFixed(1)}" y="${H - 10}" text-anchor="middle">${esc(String(p.label).slice(0, 10))}</text>`; }).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Bar chart of ${esc(c.y)} by ${esc(c.x)}">${bars}</svg>`;
}
function artifactView(runId, x) {
  const r = x.result || {};
  if (r.kind === "slideshow") return slideViewer(runId, r);
  if (r.kind === "document") return `<article class="doc"><h3>${esc(r.title)}</h3>${md(r.body)}<footer><span>${r.word_count} words · saved in your workspace</span><span class="actions">${downloadBtn(r)}<button class="link-btn" data-act="copy" data-text="${esc(`${r.title}\n\n${r.body}`)}">Copy text</button></span></footer></article>`;
  if (r.kind === "meeting") return `<article class="invite"><div class="date"><span>${esc(new Date(r.start).toLocaleDateString([], { month: "short" }))}</span><b>${esc(new Date(r.start).getDate())}</b></div><div class="what"><h3>${esc(r.title)}</h3><p class="when">${esc(whenText(r.start, r.duration_minutes))}${r.location ? " · " + esc(r.location) : ""}</p>${r.attendees.length ? `<p class="who-list">${r.attendees.map(a => `<span>${esc(a)}</span>`).join("")}</p>` : ""}${r.agenda.length ? `<ol class="agenda">${r.agenda.map(a => `<li>${esc(a)}</li>`).join("")}</ol>` : ""}<footer><span class="note">Saved, not sent</span><button class="link-btn" data-act="ics" data-title="${esc(r.title)}" data-ics="${esc(r.ics)}">${icon("download", "sm")}Calendar file</button><button class="link-btn" data-act="copy" data-text="${esc(`${r.title}\n${whenText(r.start, r.duration_minutes)}${r.location ? "\n" + r.location : ""}${r.attendees.length ? "\nWith: " + r.attendees.join(", ") : ""}${r.agenda.length ? "\n\nAgenda:\n" + r.agenda.map(a => "- " + a).join("\n") : ""}`)}">Copy details</button></footer></div></article>`;
  if (r.kind === "email") return `<article class="doc mail"><dl><dt>To</dt><dd>${r.to.length ? r.to.map(esc).join(", ") : "<span class='note'>Add a recipient</span>"}</dd><dt>Subject</dt><dd><b>${esc(r.subject)}</b></dd></dl>${md(r.body)}<footer><span>Draft saved · not sent</span><span class="actions">${downloadBtn(r)}<button class="link-btn" data-act="copy" data-text="${esc(`To: ${r.to.join(", ")}\nSubject: ${r.subject}\n\n${r.body}`)}">Copy email</button></span></footer></article>`;
  if (r.kind === "tasks") return `<article class="doc tasks"><h3>${esc(r.title)}</h3><ul>${r.tasks.map(t => `<li><span class="box" aria-hidden="true"></span><span class="t">${esc(t.text)}</span>${t.owner ? `<span class="tag">${esc(t.owner)}</span>` : ""}${t.due ? `<span class="tag due">${esc(t.due)}</span>` : ""}</li>`).join("")}</ul><footer><span>${r.task_count} task${r.task_count === 1 ? "" : "s"} · saved in your workspace</span><span class="actions">${downloadBtn(r)}<button class="link-btn" data-act="copy" data-text="${esc(`${r.title}\n` + r.tasks.map(t => `- [ ] ${t.text}${t.owner ? " (" + t.owner + ")" : ""}${t.due ? " by " + t.due : ""}`).join("\n"))}">Copy list</button></span></footer></article>`;
  if (r.kind === "analysis") return `<div class="analysis">${r.chart ? chartSvg(r.chart) : ""}<ul class="points">${r.highlights.map(h => `<li>${esc(h)}</li>`).join("")}</ul></div><p class="note result-actions">${downloadBtn(r)}</p>`;
  if (r.kind === "page_error") return `<p class="note">Couldn't open <a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.url)}</a>: ${esc(r.error)}</p>`;
  if (r.kind === "page") return `<blockquote class="source"><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title || r.url)}</a><p>${esc(r.text.slice(0, 420))}${r.text.length > 420 ? "…" : ""}</p></blockquote>`;
  if (r.source === "github_mcp") return `<details class="source"><summary>Read from ${esc(r.repository)}${r.truncated ? " · truncated" : ""}</summary><p class="note">${esc(r.scope)}</p><pre>${esc(r.text)}</pre></details>`;
  if (r.draft_id) return `<blockquote class="source"><b>Reply draft for ticket ${esc(r.ticket_id)} · saved, not sent</b><p>${esc(r.body)}</p></blockquote>`;
  if (r.tickets) return `<blockquote class="source"><b>Sample tickets</b>${r.tickets.map(t => `<p>${esc(t.id)} · ${esc(t.subject)}</p>`).join("")}</blockquote>`;
  if (r.documents) return `<blockquote class="source"><b>Sample help documents</b>${r.documents.map(d => `<p>${esc(d.title)}</p>`).join("")}</blockquote>`;
  return "";
}
/* Task answers and action summaries come from persisted backend records. */
const RECOVERY = {
  step_limit: "It used all of its tool calls before it could finish. Ask for something narrower, or try again.",
  deliverable_missing: "Nothing was saved. Try again, or name the file you want (for example, “save it as a slideshow”).",
  retry_exhausted: "The model kept failing. Wait a moment and try again.",
  provider_error: "The model provider returned an error. Try again in a moment.",
  provider_timeout: "The model took too long. Try again in a moment.",
  github_error: "GitHub couldn't be read. Check the repository link and that this connection can see it.",
  github_not_configured: "Ask an admin to prepare the GitHub connection on the server, then try again.",
  connection_denied: "Ask an admin to prepare the GitHub connection again, then try again.",
  repository_changed: "Start a new conversation to use a different repository.",
  token_budget: "This task used its model budget. Try a smaller request.",
  stale_spec: "The agent was edited while this ran. Try again.",
  history_too_long: "This conversation is too long. Start a new conversation.",
};
const wordsOf = t => new Set(String(t).toLowerCase().match(/[a-z']+/g) || []);
const similar = (a, b) => { const x = wordsOf(a), y = wordsOf(b); if (!x.size || !y.size) return false; let n = 0; x.forEach(w => { if (y.has(w)) n++; }); return n / Math.min(x.size, y.size) >= 0.7; };
function failedCard(r) {
  const hint = RECOVERY[r.error_code] || "Something went wrong with this task.";
  const said = r.error || "Stopped before finishing.";
  // The error text often already says what the hint would, so only add the hint when it adds something.
  const extra = similar(said, hint) ? "" : hint + " ";
  return `<div class="failed"><p class="err">${esc(said)}</p><p class="note">${esc(extra)}The agent is fine: send it anything else whenever you like.</p><div class="row"><button class="btn small" data-act="retry-run" data-id="${esc(r.id)}">Try again</button></div></div>`;
}
function narrate(r, arts) {
  if (r.next_attempt_at) return `<p class="note">Temporary provider issue. Retry ${esc(r.retry_count)} scheduled for ${esc(new Date(r.next_attempt_at).toLocaleTimeString())}.</p>`;
  if (r.status === "queued" || r.status === "running") return `<p class="thinking">${arts.length ? "Working on the next step" : "Thinking"}</p>`;
  if (r.status === "failed") return failedCard(r);
  if (r.status === "cancelled") return `<p class="note">Stopped.</p>`;
  if (r.status === "completed" && !r.result?.answer) return `<p class="note">${esc(r.result?.summary || "Task complete.")}</p>`;
  return "";
}
const KIND = { validation: "Check", retry: "Retry", planner: "Plan", plan: "Plan", model: "Think", tool: "Run", gate: "Ask", approval: "Ask", decision: "Review", revision: "Revise", answer: "Answer", error: "Error" };
function agentTurn(r, a) {
  const steps = S.steps[r.id]?.list || [], arts = steps.filter(s => s.kind === "tool").map(s => ({ label: s.label, result: s.data.result }));
  const ask = S.approvals.find(x => x.run_id === r.id && x.status === "pending");
  let html = arts.map(x => artifactView(r.id, x)).join("");
  html += narrate(r, arts);
  if (r.status === "completed" && r.result?.answer) html += `<div class="answer">${md(r.result.answer)}</div>`;
  if (r.status === "awaiting_approval") html += ask ? askBlock(ask) : `<p class="note">Waiting for ${esc(userName(a.manager_id))} to approve.</p>`;
  const rated = r.outcome, rateable = ["completed", "failed"].includes(r.status) && canManage(a);
  html += `<div class="turn-tools">${steps.length ? `<details class="quiet steps"><summary>${steps.length} step${steps.length === 1 ? "" : "s"}${r.mode === "demo" ? " · demo" : ""}</summary><ol>${steps.map(s => `<li><span class="k">${esc(KIND[s.kind] || s.kind)}</span><span>${esc(TOOL_VERB[s.label] || s.label)}</span><time>${since(r.created_at, s.created_at)}</time></li>`).join("")}</ol></details>` : ""}
    ${rateable ? `<span class="rate">${rated ? `<span class="note">${rated.success ? "Marked good" : "Marked poor"}</span>` : `<button class="icon-only" data-act="rate" data-id="${esc(r.id)}" data-ok="true" aria-label="Good result" title="Good result">${icon("up", "sm")}</button><button class="icon-only" data-act="rate" data-id="${esc(r.id)}" data-ok="false" aria-label="Poor result" title="Poor result">${icon("down", "sm")}</button>`}</span>` : ""}
    ${!TERMINAL.includes(r.status) ? `<button class="link-btn" data-act="cancel" data-id="${esc(r.id)}">Stop</button>` : ""}</div>`;
  return html;
}
function activeConversation(id) { return (S.conversations[id] || []).at(-1); }
function followTarget(a, runs) {
  const conv = activeConversation(a.id);
  const last = conv ? runs.find(r => r.id === conv.last_run_id) : null;
  return last && last.status === "completed" && last.mode !== "demo" ? last : null;
}
function chatScreen(id) {
  const a = agentById(id);
  if (!a) return `<div class="center-msg">${orb("missing", { size: 64 })}<h2>Agent not found</h2><p class="note">It may not be visible to this identity.</p><a class="btn" href="#/new">Build an agent</a></div>`;
  const runs = S.runs.filter(r => r.agent_id === id), follow = followTarget(a, runs), manages = canManage(a), caps = capsOf(a);
  const usable = profile(a.model_profile_id)?.enabled ? a.model_profile_id : "demo", ex = caps.map(c => EXAMPLES[c.id] || c.example).filter(Boolean), m = ui.metrics[id];
  const turns = list => { let prev = null; return list.map(r => {
    const gap = prev && prev.thread_id !== r.thread_id ? `<li class="divider"><span>New conversation</span></li>` : ""; prev = r;
    return `${gap}<li class="msg you"><p>${esc(r.task)}</p></li><li class="msg agent">${orb(a.id, { size: 28, level: a.level })}<div class="body">${agentTurn(r, a)}</div></li>`;
  }).join(""); };
  const currentThread = activeConversation(id)?.id || runs.at(-1)?.thread_id;
  const current = runs.filter(r => r.thread_id === currentThread), older = runs.filter(r => r.thread_id !== currentThread);
  const olderCount = new Set(older.map(r => r.thread_id)).size;
  const earlier = older.length ? `<details class="quiet earlier"><summary>Earlier conversations (${olderCount})</summary><ol class="thread older">${turns(older)}</ol></details>` : "";
  const thread = turns(current);
  return `<div class="chat">
    <header class="chat-top">
      <div class="who">${orb(a.id, { size: 32, level: a.level, cls: ui.fresh === a.id ? "ignite" : "" })}<div><h1>${esc(a.name)}</h1><p>${caps.map(short).map(esc).join(" · ")} · ${esc(modelLabel(a.model_profile_id))}</p></div></div>
      <div class="row">
        ${a.status === "active" && current.length ? `<button class="btn small ghost" data-act="new-thread" data-id="${esc(a.id)}" title="Start a fresh conversation with ${esc(a.name)}">${icon("plus", "sm")}New conversation</button>` : ""}
        ${perAction() ? `<button class="switch" role="switch" aria-checked="${!alone(a)}" data-act="mode" data-id="${esc(a.id)}" data-level="${alone(a) ? "intern" : "associate"}" ${manages ? "" : "disabled"}><span class="track"><span class="thumb"></span></span><span class="lbl">Ask before acting</span></button>` : ""}

      </div>
    </header>
    ${ui.rename === id ? `<form class="about row" data-form="rename" data-id="${esc(id)}"><label>Name <input name="name" value="${esc(a.name)}" maxlength="100" required></label><span class="note">Renaming stops any unfinished task.</span><button class="btn small primary">Save name</button><button class="btn small" type="button" data-act="dismiss-agent-edit">Cancel</button></form>` : ""}
    ${ui.archive === id ? `<div class="about danger-zone" role="alertdialog" aria-label="Delete ${esc(a.name)}"><p><b>Delete ${esc(a.name)}?</b> It leaves your workspace and any unfinished task stops. Past work stays in the team's audit history.</p><div class="row"><button class="btn small danger" data-act="archive-confirm" data-id="${esc(id)}">Delete agent</button><button class="btn small" data-act="dismiss-agent-edit">Cancel</button></div></div>` : ""}
    ${m ? `<section class="about"><dl><dt>Instructions</dt><dd>${esc(a.job_description)}<details class="quiet playbook-d"><summary>Full system prompt</summary><p class="note prompt">${esc(a.instructions)}</p></details></dd><dt>Tools</dt><dd>${caps.flatMap(c => c.tool_contracts).map(t => `${esc(TOOL_VERB[t.name] || t.name)} <span class="note">(${esc(RISK[t.risk] || t.risk)})</span>`).join("<br>")}</dd><dt>How it works</dt><dd>${caps.filter(c => c.skill).map(c => `<details class="quiet playbook-d"><summary>${esc(c.name)}</summary>${playbook(c.skill)}</details>`).join("") || "--"}</dd><dt>Track record</dt><dd>${m.p.approved_actions} of ${m.p.reviewed_actions} actions approved · ${m.p.successful_tasks} of ${m.p.evaluated_tasks} results marked good · ${m.p.completed_runs} of ${m.p.run_count} tasks finished</dd><dt>Team</dt><dd>${esc(deptName(a.department_id))} · managed by ${esc(userName(a.manager_id))}</dd></dl><button class="link-btn" data-act="close-about" data-id="${esc(id)}">Close</button></section>` : ""}
    ${a.status !== "active" ? `<div class="center-msg small"><p>${esc(a.name)} needs its own connection before the first task. Credentials never travel with a template.</p><button class="btn primary" data-act="activate" data-id="${esc(id)}" ${manages ? "" : "disabled"}>Connect and enable</button></div>` : ""}
    ${earlier}
    ${current.length ? `<ol class="thread">${thread}</ol>` : `<div class="hello">${orb(a.id, { size: 84, level: a.level, cls: ui.fresh === a.id ? "ignite" : "" })}<h2 class="display small">${words("What should " + a.name + " do?")}</h2><p class="note">${perAction() ? (alone(a) ? "It works on its own for reads and saves." : "It asks before every action.") : `It can ${esc(abilities(a).join(", "))}, and nothing else.`}${usable === "demo" ? " Demo model: fixed templates." : ""}</p></div>`}
    <form class="composer" data-form="run" data-id="${esc(id)}">
      ${usesGitHub(a) ? `<label class="repository-field">GitHub repository <input name="repository" data-draft="repository" data-id="${esc(id)}" value="${esc(ui.repositories[id] ?? runs.at(-1)?.repository ?? "")}" placeholder="https://github.com/owner/repository" maxlength="300" required><span class="note">Choose any repository this connection can access. Start a new conversation to switch.</span></label>` : ""}
      ${!current.length && ex.length ? `<div class="ideas">${ex.slice(0, 3).map(t => `<button type="button" class="idea" data-act="example" data-id="${esc(id)}" data-text="${esc(t)}">${esc(t)}</button>`).join("")}</div>` : ""}
      <div class="box">
        <label class="sr-only" for="task-${esc(id)}">Message ${esc(a.name)}</label>
        <textarea id="task-${esc(id)}" name="task" rows="1" data-draft="run" data-id="${esc(id)}" ${usesGitHub(a) ? "" : "required"} placeholder="${usesGitHub(a) ? (follow ? "Reply, or just press Send to run it again…" : "Optional: add details, or just press Send to start") : follow ? "Reply…" : `Message ${esc(a.name)}…`}" ${a.status === "active" ? "" : "disabled"}>${esc(ui.drafts[id] ?? "")}</textarea>
        <div class="box-row"><span class="row"><span class="model-chip ${profile(a.model_profile_id)?.enabled ? "" : "off"}" title="Chosen when this agent was created">${esc(modelLabel(a.model_profile_id))}${profile(a.model_profile_id)?.enabled ? "" : " · needs key"}</span>
          ${caps.some(c => c.tools?.includes("analyze_data")) && a.status === "active" ? `<button type="button" class="icon-only attach" data-act="attach" data-id="${esc(id)}" aria-label="Add a CSV file" title="Add a CSV file (up to about 100 rows)">${icon("attach", "sm")}</button><input type="file" class="sr-only" id="file-${esc(id)}" data-attach="${esc(id)}" accept=".csv,.tsv,.txt,text/csv,text/plain" tabindex="-1" aria-hidden="true">` : ""}
          <span class="kbd-hint note">Enter to send · Shift+Enter for a new line</span></span>
          <button class="send" aria-label="Send" ${a.status === "active" ? "" : "disabled"}>${icon("send")}</button></div>
      </div>
    </form>
  </div>`;
}

/* ---------- approvals ---------- */
function inboxScreen() {
  const pending = S.approvals.filter(a => a.status === "pending"), drafts = S.proposals.filter(p => p.status === "draft"), past = S.approvals.filter(a => a.status !== "pending");
  return `<div class="page">
    <h1 class="display">${words("Approvals")}</h1>
    <p class="lede">${perAction() ? "Agents that ask before acting wait here. Each answer covers one action." : "New agents wait here for a manager. Once approved, an agent works on its own with only the tools it was approved for."}</p>
    ${drafts.length ? `<h2 class="section">New agents</h2><ul class="lines">${drafts.map(p => { const ok = S.me.roles.includes("admin") || (S.me.roles.includes("manager") && p.spec.manager_id === user), mine = p.actor_id === user; return `<li class="proposal">${orb(p.id, { size: 26 })}<span><b>${esc(p.spec.name)}</b> <span class="note">Can ${esc(p.spec.capability_ids.map(id => capById(id)).filter(Boolean).map(c => c.name.toLowerCase()).join(", "))} · ${esc(modelLabel(p.spec.model_profile_id))} · asked by ${esc(userName(p.actor_id))} · ${esc(userName(p.spec.manager_id))} approves</span><details class="quiet"><summary>What it will do</summary><p class="note prompt">${esc(p.spec.job_description || "No description.")}</p></details></span><span class="row">${ok || mine ? `<button class="btn small ghost" data-act="reject-draft" data-id="${esc(p.id)}">${ok && !mine ? "Decline" : "Withdraw"}</button>` : ""}<button class="btn small ${ok ? "primary" : ""}" data-act="confirm-draft" data-id="${esc(p.id)}" data-rev="${p.revision}" ${ok ? "" : "disabled"}>Approve agent</button></span></li>`; }).join("")}</ul>` : ""}
    ${pending.length ? `${drafts.length ? `<h2 class="section">Actions</h2>` : ""}<div class="list">${pending.map(a => askBlock(a, true)).join("")}</div>` : ""}
    ${!pending.length && !drafts.length ? `<p class="empty-line">Nothing waiting. You're all caught up.</p>` : ""}
    ${past.length ? `<details class="quiet history"><summary>History (${past.length})</summary><ul class="lines">${past.slice().reverse().slice(0, 25).map(a => `<li><span class="dot ${a.status === "approved" ? "ok" : a.status === "rejected" ? "bad" : "warn"}"></span><span><b>${esc(agentById(a.agent_id)?.name || "Agent")}</b> <span class="note">${esc(TOOL_VERB[a.action.tool_id] || a.action.tool_id)} · ${esc(a.status.replace(/_/g, " "))}</span></span><time>${clock(a.decided_at || a.updated_at || a.created_at)}</time></li>`).join("")}</ul></details>` : ""}
  </div>`;
}

/* Files: what the agents saved, gathered from each agent's own activity. */
const FILE_KINDS = { slideshow: ["slides", "Slides"], document: ["document", "Document"], email: ["mail", "Email draft"], meeting: ["calendar", "Meeting"], tasks: ["tasks", "Task list"], analysis: ["chart", "Analysis"] };
async function loadFiles() {
  ui.files = null;
  const agents = S.agents.slice(0, 30);
  const snaps = await Promise.all(agents.map(a => api(`agents/${a.id}/activity`).catch(() => null)));
  const out = [];
  snaps.forEach((snap, i) => {
    if (!snap) return;
    const runs = new Map(snap.runs.map(r => [r.id, r]));
    for (const st of snap.steps) {
      const res = st.kind === "tool" && st.data?.result; if (!res || !FILE_KINDS[res.kind]) continue;
      out.push({ id: st.id, agent: agents[i], run: runs.get(st.run_id), at: st.created_at, result: res });
    }
  });
  ui.files = out.sort((x, y) => String(y.at).localeCompare(String(x.at)));
  if (route().name === "files") render();
}
function filesScreen() {
  const list = ui.files;
  const row = f => { const [ic, label] = FILE_KINDS[f.result.kind], title = f.result.title || f.result.subject || label, e = exportOf(f.result);
    return `<li><span class="lic">${icon(ic)}</span><span><b>${esc(title)}</b><span class="note">${esc(label)} · ${esc(f.agent.name)} · ${esc(new Date(f.at).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }))}</span></span><span class="row"><a class="btn small ghost" href="#/agent/${esc(f.agent.id)}">Open chat</a>${f.result.kind === "meeting" ? `<button class="btn small" data-act="ics" data-title="${esc(f.result.title)}" data-ics="${esc(f.result.ics)}">Calendar file</button>` : e ? `<button class="btn small" data-act="download" data-name="${esc(e.name)}" data-mime="${esc(e.mime)}" data-text="${esc(e.text)}">Download</button>` : ""}</span></li>`; };
  return `<div class="page">
    <h1 class="display">${words("Files")}</h1>
    <p class="lede">Everything your agents saved, newest first. Nothing here was sent anywhere.</p>
    ${list === null ? `<p class="empty-line">Loading your files…</p>` : list.length ? `<ul class="lines files">${list.map(row).join("")}</ul>` : `<p class="empty-line">Nothing saved yet. Ask an agent for a deck, a document, an email draft, a meeting or a task list.</p>`}
  </div>`;
}

const expandedEmployees = new Set();
document.addEventListener("toggle", event => {
  const id = event.target.dataset?.employee;
  if (id) { if (event.target.open) expandedEmployees.add(id); else expandedEmployees.delete(id); }
}, true);
function employeesScreen() {
  if (!S.employees) return '<div class="page"><h1>Manager access required</h1></div>';
  return `<div class="page"><h1 class="display">Employees</h1><p class="lede">Your people, their agents, and the work they put in motion.</p><p class="note">${esc(S.employees.scope)} · Ranked by task volume. Completed tasks are not necessarily accepted results.</p>${(() => { const quiet = S.employees.employees.filter(e => !e.agents.length && !e.runs).length; return quiet ? `<button class="link-btn" data-act="people">${ui.allPeople ? "Hide people with no activity" : `Show ${quiet} more with no activity yet`}</button>` : ""; })()}<div class="employee-grid">${S.employees.employees.filter(e => ui.allPeople || e.agents.length || e.runs).map((e, i) => `<details class="employee-card" data-employee="${esc(e.id)}" ${expandedEmployees.has(e.id) ? "open" : ""}><summary><span class="employee-avatar" aria-hidden="true">${esc(e.name[0])}</span><span class="employee-heading"><b>${esc(e.name)}</b><span class="note">${esc(e.roles.includes("admin") ? "Admin" : e.roles.includes("manager") ? "Manager" : e.roles.includes("builder") ? "Builder" : "Member")}${e.active ? "" : " · Disabled"}</span></span><span class="employee-preview">${e.agents.length} agents <span>·</span> ${e.runs} tasks</span><span class="employee-chevron" aria-hidden="true">${icon("chev")}</span></summary><div class="employee-detail"><div class="employee-metrics"><span><b>${e.agents.length}</b>Agents created</span><span><b>${e.runs}</b>Tasks run</span><span><b>${e.completed}</b>Completed</span><span><b>${e.failed}</b>Failed</span></div><p class="note">${e.input_tokens.toLocaleString()} input / ${e.output_tokens.toLocaleString()} output tokens · Provider-reported usage</p><p class="note">Last task: ${e.last_active ? esc(new Date(e.last_active).toLocaleString()) : "No activity yet"}</p><ul class="employee-agents">${e.agents.map(a => `<li><a href="#/agent/${esc(a.id)}">${esc(a.name)}</a><span class="note">${esc(a.status)} · ${a.performance?.result_eligible ? pct(a.performance.task_success_rate) + " rated good" : "Not enough ratings"}</span></li>`).join("") || '<li class="note">No agents created yet</li>'}</ul></div></details>`).join("")}</div></div>`;
}

/* ---------- leaderboard ---------- */
const bar = f => `<svg class="bar-line" viewBox="0 0 100 4" preserveAspectRatio="none" aria-hidden="true"><rect width="100" height="4" rx="2" class="bg"/><rect width="${Math.max(0, Math.min(100, (f || 0) * 100)).toFixed(1)}" height="4" rx="2" class="fg"/></svg>`;
function leaderboardScreen() {
  const lb = S.leaderboard, tab = (k, t, cur, act) => `<button data-act="${act}" data-tab="${k}" aria-pressed="${cur === k}">${t}</button>`;
  let rows = "";
  if (ui.board === "agents") {
    const mode = ui.rank, key = mode === "results" ? "result_eligible" : "eligible", need = mode === "results" ? lb.minimum_rated_tasks : lb.minimum_reviewed_actions;
    const val = r => (mode === "results" ? r.task_success_rate : r.approval_rate), count = r => (mode === "results" ? r.rated_tasks : r.reviewed_actions);
    const ranked = lb.agents.filter(r => r[key]).sort((x, y) => val(y) - val(x) || count(y) - count(x)), unranked = lb.agents.filter(r => !r[key]).sort((x, y) => count(y) - count(x));
    const list = ranked.map((r, i) => { const a = agentById(r.agent_id); return `<li class="${i === 0 ? "first" : ""}"><span class="rk">${i + 1}</span><a class="who" href="#/agent/${esc(r.agent_id)}">${orb(r.agent_id, { size: 30, level: a?.level })}${esc(r.name)}</a><span class="meter">${bar(val(r))}</span><b class="score">${pct(val(r))}</b></li>`; }).join("")
      + unranked.map(r => { const a = agentById(r.agent_id); return `<li class="pending"><span class="rk">–</span><a class="who" href="#/agent/${esc(r.agent_id)}">${orb(r.agent_id, { size: 30, level: a?.level })}${esc(r.name)}</a><span class="meter">${bar(count(r) / need)}</span><span class="note score">${count(r)} of ${need}</span></li>`; }).join("");
    rows = `<div class="tabs-line sub">${tab("results", "Result quality", mode, "rank")}${tab("approvals", "Approval rate", mode, "rank")}</div><p class="note">${mode === "results" ? `Share of results marked good. Ranked after ${need} ratings.` : `Share of actions approved. Ranked after ${need} reviews.`}</p>${lb.agents.length ? `<ol class="board">${list}</ol>` : `<p class="empty-line">No agents yet. Build one and rate its results.</p>`}`;
  } else {
    const list = ui.board === "capabilities" ? lb.capability_usage : lb.creator_usage, max = Math.max(1, ...list.map(r => r.agents));
    rows = list.length ? `<ol class="board">${list.map((r, i) => { const c = capById(r.capability_id); return `<li class="${i === 0 ? "first" : ""}"><span class="rk">${i + 1}</span><span class="who">${ui.board === "capabilities" ? `${icon(c?.icon || "tool")}${esc(c ? c.name : r.capability_id)} <span class="note">by ${esc(userName(r.creator_id))}</span>` : esc(userName(r.creator_id))}</span><span class="meter">${bar(r.agents / max)}</span><b class="score">${r.agents}</b></li>`; }).join("")}</ol><p class="note">Counted by how many active agents use them.</p>` : `<p class="empty-line">Nothing to rank yet.</p>`;
  }
  return `<div class="page">
    <h1 class="display">${words("Leaderboard")}</h1>
    <p class="lede">Scores come from what managers actually approved and rated.</p>
    <div class="tabs-line">${tab("agents", "Agents", ui.board, "board")}${tab("capabilities", "Tools", ui.board, "board")}${tab("creators", "Creators", ui.board, "board")}</div>
    ${rows}</div>`;
}

/* ---------- library ---------- */
function libraryScreen() {
  const usage = id => S.leaderboard.capability_usage.find(u => u.capability_id === id)?.agents || 0;
  const listings = S.marketplace.filter(l => l.kind === "agent");
  const github = S["integrations/github"] || {};
  const source = ui.newTool.source || (github.connected ? "github" : "bundle");
  // GitHub setup only shows up once someone picks GitHub below. After it's prepared, its tool appears in the list by itself.
  const isAdmin = S.me.roles.includes("admin");
  const setup = github.connected ? "" : !github.configured
    ? `<p class="note gh-note">GitHub reading needs a token on the server. Add <b>GITHUB_PERSONAL_ACCESS_TOKEN</b> to the server's <b>.env</b>, restart, then come back here.</p>`
    : isAdmin
      ? `<div class="gh-card"><span class="gh-text">${icon("tool")}<span>GitHub isn't ready yet. Enter a repository the server's GitHub token can read to test it. This turns GitHub on for your departments.</span></span><label class="gh-field">Repository to test <input id="gh-repo" form="gh-none" maxlength="300" placeholder="owner/repository" autocomplete="off"></label><button type="button" class="btn small primary" data-act="gh-prepare">Prepare GitHub</button></div>`
      : `<p class="note gh-note">GitHub isn't ready yet. Ask an admin to prepare it, then come back here.</p>`;
  const add = `<details class="quiet add-library-tool"><summary>Add a tool</summary><form class="stack" data-form="new-cap">
    ${isManager() ? "" : `<p class="note">You can explore this form. Sign in with a manager or admin account to add tools to the Library.</p>`}
    <label>Name <input name="name" data-draft="new-tool-name" value="${esc(ui.newTool.name)}" required maxlength="100" placeholder="Repository Reader"></label>
    <label>What should it do? <textarea name="description" data-draft="new-tool-description" required maxlength="1000" rows="2" placeholder="Read a repository and explain its purpose, code and open issues.">${esc(ui.newTool.description)}</textarea></label>
    <div class="field"><span class="label">Use</span><input type="hidden" name="source" value="${esc(source)}">${dropdown({ field: "new-tool-source", value: source, label: "Where the tool gets its abilities", options: [["github", github.connected ? "GitHub · connected" : "GitHub · needs setup"], ["bundle", "Existing workspace tools"]] })}</div>
    ${source === "github" && !github.connected ? setup : source === "github" ? `<div class="field"><span class="label">Department</span><input type="hidden" name="department_id" value="${esc(ui.newTool.department || defaultDept())}">${dropdown({ field: "new-tool-department", value: ui.newTool.department || defaultDept(), label: "Department", options: S.departments.filter(d => github.department_ids?.includes(d.id)).map(d => [d.id, d.name]) })}</div><p class="note">Reads files and issues. Choose the repository when assigning a task.</p>` : `<div class="checks">${Object.entries(TOOL_VERB).filter(([k]) => !k.startsWith("github_")).map(([k,v]) => `<label><input type="checkbox" name="tools" value="${esc(k)}">${esc(v[0].toUpperCase()+v.slice(1))}</label>`).join("")}</div>`}
    <div><button class="btn small primary" ${isManager() && !(source === "github" && !github.connected) ? "" : "disabled"}>Add tool</button></div></form></details>`;
  const tools = `<ul class="lines tools">${S.capabilities.map(c => `<li><span class="lic">${icon(c.icon || "tool")}</span><span><b>${esc(c.name)}</b><span class="note" title="Added by ${esc(userName(c.creator_id))}">${esc(c.description)}</span><span class="note meta">${esc([...new Set(c.tool_contracts.map(t => RISK[t.risk] || t.risk))].join(", "))}${usage(c.id) ? ` · used by ${usage(c.id)} agent${usage(c.id) === 1 ? "" : "s"}` : ""}</span>${c.skill ? `<details class="quiet playbook-d"><summary>Playbook</summary>${playbook(c.skill)}</details>` : ""}</span><button class="btn small" data-act="use-cap" data-id="${esc(c.id)}" ${canHire() ? "" : "disabled"}>Use</button></li>`).join("")}</ul>`;
  const shared = listings.length ? `<ul class="lines">${listings.map(l => `<li>${orb(l.id, { size: 26 })}<span><b>${esc(l.payload.name)}</b><span class="note">${esc(l.payload.job_description)} · by ${esc(userName(l.creator_id || l.publisher_id))} · ${l.installation_count} install${l.installation_count === 1 ? "" : "s"}</span></span><form data-form="install" data-id="${esc(l.id)}"><button class="btn small" ${canHire() ? "" : "disabled"}>Install</button></form></li>`).join("")}</ul>` : `<p class="empty-line">Nothing shared yet. Open an agent's menu and choose “Share as template”.</p>`;
  return `<div class="page">
    <h1 class="display">${words("Library")}</h1>
    <p class="lede">Tools your company set up once, and agents your team shared.</p>
    <div class="tabs-line"><button data-act="lib" data-tab="capabilities" aria-pressed="${ui.lib === "capabilities"}">Tools</button><button data-act="lib" data-tab="agents" aria-pressed="${ui.lib === "agents"}">Shared agents</button></div>
    ${ui.lib === "capabilities" ? tools + add : shared}</div>`;
}

/* ---------- atomic create flow ---------- */
async function createAgent() {
  const target = forge.target && agentById(forge.target);
  if (!forge.caps.length && !forge.text.trim()) throw Error("Add instructions or choose a tool.");
  if (!target && !forge.name.trim()) throw Error("Name your agent.");
  if (!target && nameTaken(forge.name)) throw Error(`An agent called ${forge.name.trim()} already exists. Pick another name.`);
  if (target) {
    const a = await api(`agents/${target.id}/capabilities`, "POST", { capability_ids: forge.caps, expected_spec_version: target.spec_version });
    forge = forge0(); location.hash = "#/agent/" + a.id;
    return perAction() ? `${a.name} is ready. New tools ask before acting.` : `${a.name} can now use its new tools.`;
  }
  if (forge.caps.some(id => capById(id)?.tools?.some(t => t.startsWith("github_"))) && forge.mode === "demo") throw Error("Choose Meta or Gemini for GitHub reading. Demo mode does not read GitHub.");
  const body = { model_profile_id: forge.mode, department_id: defaultDept(), manager_id: defaultManager() };
  if (forge.caps.length) body.capability_ids = forge.caps;
  if (forge.text.trim()) body.description = forge.text.trim();
  if (forge.name.trim()) body.name = forge.name.trim();
  const result = await api("agents/quick-create", "POST", body);
  forge = forge0();
  if (result.status === "awaiting_confirmation") {
    location.hash = "#/inbox";
    return `${result.proposal.spec.name} is waiting for ${userName(result.proposal.spec.manager_id)} to confirm.`;
  }
  ui.fresh = result.agent.id; location.hash = "#/agent/" + result.agent.id;
  return null;
}

/* ---------- events ---------- */
function toggleTool(id) {
  const adding = !forge.caps.includes(id);
  forge.caps = adding ? [...forge.caps, id] : forge.caps.filter(c => c !== id);
  ui.caption = adding ? id : null;
  if (adding) ui.pulse++;
  render(); ($(`.orbit [data-id="${id}"]`) || $(`.belt [data-id="${id}"]`))?.focus({ preventScroll: true });
}
document.addEventListener("click", e => {
  const b = e.target.closest("[data-act]"); if (!b) return;
  const { act: kind, id } = b.dataset;
  if (kind === "tool") toggleTool(id);
  if (kind === "more-tools") { forge.more = true; render(); }
  if (kind === "role") {
    const r = ROLES.find(x => x.id === b.dataset.id); if (!r) return;
    forge.text = r.text; forge.caps = [...new Set([...forge.caps, ...r.caps.filter(capById)])];
    if (!forge.name.trim() || forge.autoName) { forge.name = uniqueName(r.name); forge.autoName = true; }
    ui.pulse++; render(); const t = $("#forge-text"); if (t) { grow(t); t.focus(); }
  }
  if (kind === "pick") {
    const v = b.dataset.value;
    if (b.dataset.field === "new-tool-source") { ui.newTool.source = v; render(); $(".add-library-tool")?.setAttribute("open", ""); }
    if (b.dataset.field === "new-tool-department") { ui.newTool.department = v; render(); $(".add-library-tool")?.setAttribute("open", ""); }
    if (b.dataset.field === "forge-mode") { forge.mode = v; render(); }
    if (b.dataset.field === "identity") { const sel = $("#identity"); if (sel && sel.value !== v) { sel.value = v; sel.dispatchEvent(new Event("change", { bubbles: true })); } b.closest("details")?.removeAttribute("open"); }
  }
  if (kind === "idea") { forge.text = b.dataset.text; render(); const t = $("#forge-text"); if (t) { grow(t); t.focus(); t.setSelectionRange(t.value.length, t.value.length); } }
  if (kind === "create") act(createAgent, b);
  if (kind === "confirm-draft") act(async () => { const a = await api(`recruiter/proposals/${id}/confirm`, "POST", { revision: Number(b.dataset.rev) }); ui.fresh = a.id; location.hash = "#/agent/" + a.id; return null; }, b);
  if (kind === "reject-draft") act(async () => { await api(`recruiter/proposals/${id}/reject`, "POST", {}); return "Request closed. Nothing was created."; }, b);
  if (kind === "use-cap") { forge = { ...forge0(), caps: [id] }; location.hash = "#/new"; render(); }
  if (kind === "teach") { b.closest("details")?.removeAttribute("open"); forge = { ...forge0(), target: id }; location.hash = "#/new"; render(); }
  if (kind === "mode") { const a = agentById(id); if (a) act(async () => { await api(`agents/${id}/level`, "POST", { level: b.dataset.level, reason: "Switched from the agent page." }); return b.dataset.level === "intern" ? `${a.name} will ask before every action.` : `${a.name} now works on its own for reads and saves.`; }, b); }
  if (kind === "example") { ui.drafts[id] = b.dataset.text; render(); const t = $("[data-draft='run']"); if (t) { grow(t); t.focus(); t.setSelectionRange(t.value.length, t.value.length); } }
  if (kind === "new-thread") act(async () => { await api(`agents/${id}/conversations`, "POST", {}); return "Your next message starts a new conversation."; }, b);
  if (["rename", "archive", "perf", "new-thread"].includes(kind) && b.closest(".agent-menu")) {
    b.closest("details")?.removeAttribute("open");
    location.hash = "#/agent/" + id;
    document.body.classList.remove("side-open");
  }
  if (kind === "rename" || kind === "archive") {
    b.closest("details")?.removeAttribute("open");
    ui.rename = kind === "rename" ? id : null; ui.archive = kind === "archive" ? id : null;
    ui.stick = false; render(); ui.stick = true;
    scrollTo({ top: 0 }); $(kind === "rename" ? `form[data-form="rename"] input` : `[data-act="archive-confirm"]`)?.focus({ preventScroll: true });
  }
  if (kind === "dismiss-agent-edit") { ui.rename = null; ui.archive = null; render(); }
  if (kind === "archive-confirm") act(async () => { await api(`agents/${id}`, "DELETE"); ui.archive = null; location.hash = "#/new"; return "Agent deleted."; }, b);
  if (kind === "revise") { ui.revise[id] = !ui.revise[id]; ui.stick = false; render(); ui.stick = true; $(`form[data-id="${id}"] input`)?.focus(); }
  if (kind === "slide") goSlide(b.dataset.run, Number(b.dataset.to));
  if (kind === "download") saveFile(b.dataset.name, b.dataset.mime, b.dataset.text);
  if (kind === "attach") $(`#file-${id}`)?.click();
  if (kind === "ics") { const url = URL.createObjectURL(new Blob([b.dataset.ics], { type: "text/calendar" })), a = document.createElement("a"); a.href = url; a.download = (b.dataset.title || "meeting").replace(/[^\w -]+/g, "").trim().replace(/\s+/g, "-").toLowerCase() + ".ics"; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  if (kind === "copy") navigator.clipboard?.writeText(b.dataset.text).then(() => toast("Copied."), () => toast("Couldn't copy. Select the text instead.", true));
  if (kind === "rate") act(async () => { await api(`runs/${id}/outcome`, "POST", { success: b.dataset.ok === "true", comment: b.dataset.ok === "true" ? "Manager rated the result good." : "Manager rated the result poor." }); return "Thanks. That counts toward the leaderboard."; }, b);
  if (kind === "retry-run") {
    const r = S.runs.find(x => x.id === id), a = r && agentById(r.agent_id); if (!a) return;
    act(async () => {
      const body = { task: r.task };
      if (r.repository) body.repository = r.repository;
      const conv = activeConversation(a.id); if (conv) body.conversation_id = conv.id;
      await api(`agents/${a.id}/runs`, "POST", body); return null;
    }, b);
  }
  if (kind === "cancel") act(async () => { await api(`runs/${id}/cancel`, "POST", {}); return null; }, b);
  if (kind === "activate") act(async () => {
    const a = agentById(id), ids = a.required_capabilities?.map(c => c.id) || a.bindings.map(x => x.capability_id), bindings = [];
    for (const cid of ids) { const conn = capById(cid)?.connection_id || "support-local", v = await api(`capabilities/${cid}/validate`, "POST", { department_id: a.department_id, connection_id: conn }); bindings.push({ capability_id: cid, connection_id: conn, validation_id: v.id }); }
    await api(`agents/${a.id}`, "PATCH", { bindings, expected_spec_version: a.spec_version });
    return `${a.name} is connected and ready.`;
  }, b);
  if (kind === "perf") { b.closest("details")?.removeAttribute("open"); (async () => { try { const [p, v] = await Promise.all([api(`agents/${id}/performance`), api(`agents/${id}/versions`)]); ui.metrics[id] = { p, v }; ui.stick = false; render(); ui.stick = true; scrollTo({ top: 0, behavior: "smooth" }); } catch (err) { toast(err.message, true); } })(); }
  if (kind === "close-about") { delete ui.metrics[id]; render(); }
  if (kind === "share-agent") { b.closest("details")?.removeAttribute("open"); act(async () => { await api("marketplace", "POST", { kind: "agent", source_id: id }); return "Shared in the Library. No connections or trust included."; }, b); }
  if (kind === "people") { ui.allPeople = !ui.allPeople; render(); }
  if (kind === "rank") { ui.rank = b.dataset.tab; render(); }
  if (kind === "board") { ui.board = b.dataset.tab; render(); }
  if (kind === "lib") { ui.lib = b.dataset.tab; render(); }
  if (kind === "gh-prepare") {
    const repo = ($("#gh-repo")?.value || "").trim();
    if (!repo) { toast("Enter a repository to test, like owner/repository.", true); $("#gh-repo")?.focus(); return; }
    act(async () => {
      for (const dep of S.departments) await api("integrations/github/connect", "POST", { repository: repo, department_id: dep.id });
      return "GitHub is ready. Read GitHub repositories is now in your tools.";
    }, b).then(() => $(".add-library-tool")?.setAttribute("open", ""));
  }
});

function goSlide(runId, to, focus = false) {
  ui.slide[runId] = Math.max(0, to); ui.stick = false; render(); ui.stick = true;
  if (focus) $(`.stage[data-run="${runId}"]`)?.focus({ preventScroll: true });
}
/* Slides: arrow keys and swipe work as well as the buttons. */
document.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.id === "gh-repo") { e.preventDefault(); $('[data-act="gh-prepare"]')?.click(); }
  
  const st = e.target.closest?.(".stage[data-run]"); if (!st || !["ArrowLeft", "ArrowRight"].includes(e.key)) return;
  const n = Number(st.dataset.n), cur = Math.min(ui.slide[st.dataset.run] || 0, n - 1), to = cur + (e.key === "ArrowRight" ? 1 : -1);
  if (to < 0 || to > n - 1) return; e.preventDefault(); goSlide(st.dataset.run, to, true);
});
let swipe = null;
document.addEventListener("pointerdown", e => { const st = e.target.closest?.(".stage[data-run]"); swipe = st && !e.target.closest("button") && e.pointerType === "touch" ? { run: st.dataset.run, n: Number(st.dataset.n), x: e.clientX, y: e.clientY } : null; });
document.addEventListener("pointerup", e => {
  if (!swipe) return; const dx = e.clientX - swipe.x, dy = e.clientY - swipe.y, s = swipe; swipe = null;
  if (Math.abs(dx) < 48 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
  const cur = Math.min(ui.slide[s.run] || 0, s.n - 1), to = cur + (dx < 0 ? 1 : -1);
  if (to >= 0 && to < s.n) goSlide(s.run, to);
});
/* Drag and drop: tools onto the core. Clicking a tool (or Enter/Space) does the same thing. */
const dropTarget = e => { const z = e.target.closest?.("[data-drop]"); return z && (z.dataset.drop === "core" ? ui.dragFrom === "belt" : ui.dragFrom === "orbit") ? z : null; };
document.addEventListener("dragstart", e => {
  const t = e.target.closest?.(".tool[data-id]"); if (!t) return;
  e.dataTransfer.setData("text/plain", t.dataset.id); e.dataTransfer.effectAllowed = "copyMove"; t.classList.add("lifted");
  ui.dragFrom = t.dataset.from === "orbit" ? "orbit" : "belt";
  document.body.classList.add(ui.dragFrom === "orbit" ? "dragging-out" : "dragging");
  const cap = $("#tool-caption"); if (cap) cap.textContent = ui.dragFrom === "orbit" ? "Drop it back down here to remove it." : "Drop it on the core.";
});
document.addEventListener("dragend", e => { e.target.closest?.(".tool")?.classList.remove("lifted"); document.body.classList.remove("dragging", "dragging-out"); ui.dragFrom = null; $$("[data-drop]").forEach(z => z.classList.remove("over")); const cap = $("#tool-caption"); if (cap) cap.textContent = toolCaption(); });
document.addEventListener("dragover", e => { const z = dropTarget(e); if (!z) return; e.preventDefault(); e.dataTransfer.dropEffect = z.dataset.drop === "core" ? "copy" : "move"; z.classList.add("over"); });
document.addEventListener("dragleave", e => { const z = e.target.closest?.("[data-drop]"); if (z && !z.contains(e.relatedTarget)) z.classList.remove("over"); });
document.addEventListener("drop", e => {
  const z = dropTarget(e); if (!z) return; e.preventDefault();
  const id = e.dataTransfer.getData("text/plain"); document.body.classList.remove("dragging", "dragging-out"); ui.dragFrom = null;
  const onCore = forge.caps.includes(id);
  if (id && capById(id) && (z.dataset.drop === "core" ? !onCore : onCore)) toggleTool(id); else z.classList.remove("over");
});
/* Tool captions: hover or focus a tool to read what it does (touch shows it after a tap). */
const showCaption = e => { const t = e.target.closest?.(".belt .tool[data-id]"); const cap = $("#tool-caption"), c = t && capById(t.dataset.id); if (cap && c && !ui.dragFrom) cap.textContent = `${short(c)}: ${c.description}`; };
document.addEventListener("pointerover", e => { if (e.pointerType !== "touch") showCaption(e); });
document.addEventListener("focusin", showCaption);
document.addEventListener("pointerout", e => { if (e.target.closest?.(".belt .tool[data-id]") && !ui.dragFrom) { const cap = $("#tool-caption"); if (cap) cap.textContent = toolCaption(); } });
/* Menus that would run off the bottom of the screen open upward instead. */
document.addEventListener("toggle", e => {
  const d = e.target; if (!d.matches?.("details.dd") || !d.open) return;
  const pop = d.querySelector(".dd-pop"); d.classList.remove("flip"); if (!pop) return;
  const r = d.getBoundingClientRect();
  if (r.bottom + pop.offsetHeight + 12 > innerHeight && r.top > pop.offsetHeight + 12) d.classList.add("flip");
}, true);

document.addEventListener("submit", e => {
  const f = e.target, kind = f.dataset.form; if (!kind) return; e.preventDefault();
  const d = Object.fromEntries(new FormData(f)), sub = e.submitter;
  if (sub?.name) d[sub.name] = sub.value;
  if (kind === "run") {
    const a = agentById(f.dataset.id), follow = followTarget(a, S.runs.filter(r => r.agent_id === a.id));
    // A GitHub agent already has its job in its instructions, so an empty message just starts it.
    const task = d.task.trim() || (usesGitHub(a) ? "Do your assigned job on this repository." : "");
    if (!task) return;
    act(async () => {
      // The agent's model was fixed when it was created; the server owns the tool-call budget.
      const body = { task };
      if (usesGitHub(a)) body.repository = d.repository;
      const conv = activeConversation(a.id);
      if (conv) body.conversation_id = conv.id;
      if (follow) body.follow_up_of = follow.id;
      await api(`agents/${a.id}/runs`, "POST", body);
      ui.drafts[a.id] = "";
      return null;
    }, sub || f.querySelector(".send")).then(() => requestAnimationFrame(() => { const t = $("[data-draft='run']"); if (t && !t.disabled && document.activeElement === document.body) t.focus({ preventScroll: true }); }));
  }
  if (kind === "rename") act(async () => { const a = agentById(f.dataset.id); await api(`agents/${a.id}`, "PATCH", { name: d.name, expected_spec_version: a.spec_version }); ui.rename = null; return "Name saved."; }, sub);
  if (kind === "decide") act(async () => { await api(`approvals/${f.dataset.id}/decision`, "POST", d); delete ui.revise[f.dataset.id]; return { approve: null, reject: "Okay. That action won't run.", request_revision: "Sent back. It will propose something new." }[d.decision]; }, sub);
  if (kind === "install") act(async () => { const r = await api(`marketplace/${f.dataset.id}/install`, "POST", { department_id: defaultDept(), manager_id: defaultManager() }); location.hash = "#/agent/" + r.resource.id; return "Installed. Connect it before its first task."; }, sub);
  if (kind === "new-cap") act(async () => {
    const body = {name: d.name, description: d.description, source: d.source};
    if (d.source === "github") body.department_id = d.department_id;
    else { body.tools = new FormData(f).getAll("tools"); if (!body.tools.length) throw Error("Choose at least one action."); }
    await api("capabilities", "POST", body);
    ui.newTool = {source: null, name: "", description: "", department: null};
    return "Tool added to Library. Use it alongside Slides or Documents.";
  }, sub);
});

/* Text boxes grow with what you type. */
function grow(t) { t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 220) + "px"; }
document.addEventListener("input", e => {
  const t = e.target.dataset?.draft; if (!t) return;
  if (t === "forge-text") { forge.text = e.target.value; grow(e.target); syncCreate(); }
  if (t === "forge-name") { forge.name = e.target.value; forge.autoName = false; syncCreate(); }
  if (t === "run") { ui.drafts[e.target.dataset.id] = e.target.value; grow(e.target); }
  if (t === "repository") ui.repositories[e.target.dataset.id] = e.target.value;
  if (t === "new-tool-name") ui.newTool.name = e.target.value;
  if (t === "new-tool-description") ui.newTool.description = e.target.value;
});
const TASK_LIMIT = 4000;
document.addEventListener("change", async e => {
  const agentId = e.target.dataset?.attach;
  if (agentId) {
    const file = e.target.files?.[0]; e.target.value = ""; if (!file) return;
    const text = (await file.text()).replace(/\r\n?/g, "\n").trim(), head = ui.drafts[agentId]?.trim() ? ui.drafts[agentId].trim() + "\n\n" : "Analyze this data:\n";
    if ((head + text).length > TASK_LIMIT) { toast(`${file.name} is too long for one message (about ${TASK_LIMIT.toLocaleString()} characters, roughly 100 rows). Keep only the columns you need.`, true); return; }
    ui.drafts[agentId] = head + text; render();
    const t = $("[data-draft='run']"); if (t) { grow(t); t.focus(); }
    toast(`Added ${file.name} (${Math.max(0, text.split("\n").length - 1)} rows).`); return;
  }
  const kind = e.target.dataset?.draft;
  if (kind === "forge-mode") { forge.mode = e.target.value; render(); }
});
document.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.target.matches?.("textarea[data-draft='run']")) { e.preventDefault(); e.target.form.requestSubmit(); }
  if (e.key === "Enter" && !e.isComposing && (e.metaKey || e.ctrlKey) && e.target.matches?.("#forge-text")) { e.preventDefault(); if (createState().ok) $("[data-act='create']")?.click(); else if (!forge.name.trim()) $("[data-draft='forge-name']")?.focus(); else syncCreate(); }
  if (e.key === "Enter" && !e.isComposing && e.target.matches?.("[data-draft='forge-name']")) { e.preventDefault(); if (createState().ok) $("[data-act='create']")?.click(); }
  if (e.key === "Escape") { $$("details.menu[open]").forEach(d => d.removeAttribute("open")); document.body.classList.remove("side-open"); }
});
document.addEventListener("click", e => { $$("details.menu[open]").forEach(d => { if (!d.contains(e.target)) d.removeAttribute("open"); }); });
$("#identity").addEventListener("change", e => { if (authMode === "password") return; user = e.target.value; sessionStorage.setItem("dev-user", user); forge = forge0(); S.steps = {}; S.conversations = {}; activityConnection?.controller.abort(); activityConnection = null; act(async () => `Signed in as ${userName(user)}.`); });
// Resize only the desktop shell; the mobile drawer keeps its existing behavior.
(() => {
  const handle = $("#side-resize"), root = document.documentElement;
  const widthKey = "agent-sidebar-width";
  const applyWidth = value => {
    const width = Math.max(200, Math.min(420, Math.round(value)));
    root.style.setProperty("--side", `${width}px`);
    handle.setAttribute("aria-valuenow", String(width));
    return width;
  };
  const saveWidth = () => { try { localStorage.setItem(widthKey, handle.getAttribute("aria-valuenow")); } catch {} };
  try { const saved = Number(localStorage.getItem(widthKey)); if (Number.isFinite(saved) && saved >= 200) applyWidth(saved); } catch {}
  let dragging = false;
  const finish = () => { if (!dragging) return; dragging = false; document.body.classList.remove("resizing-side"); saveWidth(); };
  handle.addEventListener("pointerdown", event => {
    if (event.button !== 0 || !matchMedia("(min-width:901px)").matches) return;
    event.preventDefault(); dragging = true; handle.setPointerCapture(event.pointerId);
    document.body.classList.add("resizing-side");
  });
  handle.addEventListener("pointermove", event => { if (dragging) applyWidth(event.clientX); });
  handle.addEventListener("pointerup", finish);
  handle.addEventListener("pointercancel", finish);
  handle.addEventListener("lostpointercapture", finish);
  handle.addEventListener("dblclick", () => { applyWidth(250); saveWidth(); });
  handle.addEventListener("keydown", event => {
    const current = Number(handle.getAttribute("aria-valuenow"));
    const values = { ArrowLeft: current - 10, ArrowRight: current + 10, Home: 200, End: 420 };
    if (!(event.key in values)) return;
    event.preventDefault(); applyWidth(values[event.key]); saveWidth();
  });
})();
$("#menu-btn").addEventListener("click", () => document.body.classList.toggle("side-open"));
$("#scrim").addEventListener("click", () => document.body.classList.remove("side-open"));
addEventListener("hashchange", async () => { document.body.classList.remove("side-open"); if (route().name === "files") loadFiles(); if (route().name === "agent") await loadSteps().catch(() => {}); syncActivityStream(); render(); enter(); if (route().name !== "agent") scrollTo({ top: 0 }); });

/* ---------- sky: a planet's horizon catching first light. One canvas; it breathes slowly. ---------- */
function startSky() {
  const cv = $("#sky"), ctx = cv?.getContext("2d"); if (!ctx) return;
  const still = matchMedia("(prefers-reduced-motion: reduce)");
  const stars = Array.from({ length: 150 }, () => [Math.random(), Math.random() * 0.8, Math.random() * 1.1 + 0.3, Math.random() * 6.28]);
  let W = 0, H = 0, raf = 0, px = 0, py = 0, tx = 0, ty = 0, f = 0.6, fade = 1;
  const size = () => { const d = Math.min(devicePixelRatio || 1, 2); W = innerWidth; H = innerHeight; cv.width = W * d; cv.height = H * d; ctx.setTransform(d, 0, 0, d, 0, 0); };
  /* Where the horizon sits: behind the core on the creator, low behind the message box in a chat. */
  const goal = () => ({ new: W < 620 ? 0.5 : W > 1100 ? 0.45 : 0.53, agent: 0.97 }[document.body.dataset.view] ?? 0.86);
  /* Where text scrolls across the horizon, the light dims so nothing is struck through. */
  const want = () => { const v = document.body.dataset.view, tall = document.documentElement.scrollHeight > H * 1.12; return v === "agent" ? 1 : v === "new" ? Math.max(0, 1 - scrollY / 220) : tall ? 0.22 : 1; };
  function draw(t) {
    const breathe = 0.86 + 0.14 * Math.sin(t / 2800);
    f += (goal() - f) * 0.035; fade += (want() - fade) * (still.matches ? 1 : 0.12);
    ctx.clearRect(0, 0, W, H);
    for (const [x, y, r, ph] of stars) { ctx.fillStyle = `rgba(210,225,255,${(0.2 + 0.4 * Math.abs(Math.sin(t / 2200 + ph))).toFixed(3)})`; ctx.fillRect(x * W - px * 8, y * H - py * 6, r, r); }
    ctx.globalAlpha = fade;
    const R = Math.max(W * 0.95, H * 1.2), cx = (W > 900 ? W * 0.5 + 125 : W * 0.5) + px * 18, top = H * f + py * 10, cy = top + R;
    const body = ctx.createRadialGradient(cx, top + R * 0.12, R * 0.1, cx, cy, R);
    body.addColorStop(0, "#0c1426"); body.addColorStop(0.35, "#050a16"); body.addColorStop(1, "#020308");
    for (const [w, a, col] of [[120, 0.07, "90,150,255"], [54, 0.12, "130,195,255"], [18, 0.26, "200,236,255"], [2.5, 0.9, "248,252,255"]]) {
      ctx.beginPath(); ctx.arc(cx, cy, R, Math.PI * 1.02, Math.PI * 1.98); ctx.strokeStyle = `rgba(${col},${(a * breathe).toFixed(3)})`; ctx.lineWidth = w; ctx.stroke();
    }
    ctx.beginPath(); ctx.arc(cx, cy, R - 1.2, 0, 6.2832); ctx.fillStyle = body; ctx.fill();
    const glow = Math.min(W, H) * 0.5 * breathe, sun = ctx.createRadialGradient(cx, top, 0, cx, top, glow);
    sun.addColorStop(0, "rgba(255,255,255,.85)"); sun.addColorStop(0.05, "rgba(225,242,255,.45)"); sun.addColorStop(0.25, "rgba(120,180,255,.11)"); sun.addColorStop(1, "rgba(80,140,255,0)");
    ctx.fillStyle = sun; ctx.fillRect(0, 0, W, H);
    const streak = ctx.createLinearGradient(cx - W * 0.32, 0, cx + W * 0.32, 0);
    streak.addColorStop(0, "rgba(160,210,255,0)"); streak.addColorStop(0.5, `rgba(240,250,255,${(0.45 * breathe).toFixed(3)})`); streak.addColorStop(1, "rgba(160,210,255,0)");
    ctx.fillStyle = streak; ctx.fillRect(cx - W * 0.32, top - 0.6, W * 0.64, 1.2);
    ctx.globalAlpha = 1;
  }
  function frame(t) { px += (tx - px) * 0.03; py += (ty - py) * 0.03; draw(t); raf = requestAnimationFrame(frame); }
  const start = () => { cancelAnimationFrame(raf); size(); if (still.matches) { f = goal(); draw(0); } else raf = requestAnimationFrame(frame); };
  addEventListener("resize", start);
  addEventListener("pointermove", e => { tx = e.clientX / innerWidth - 0.5; ty = e.clientY / innerHeight - 0.5; }, { passive: true });
  document.addEventListener("visibilitychange", () => { cancelAnimationFrame(raf); if (!document.hidden) start(); });
  addEventListener("hashchange", () => { if (still.matches) setTimeout(() => { f = goal(); draw(0); }, 0); });
  addEventListener("scroll", () => { if (still.matches) draw(0); }, { passive: true });
  still.addEventListener?.("change", start);
  start();
}

async function authenticate() {
  const response = await fetch("/api/auth/config");
  if (!response.ok) throw Error("Authentication configuration is unavailable.");
  const config = await response.json(); authMode = config.mode;
  if (authMode !== "password") return;
  $("#identity").disabled = true;
  $("#identity").setAttribute("aria-label", "Signed in account");
  const identityLabel = document.querySelector("label.identity span"); if (identityLabel) identityLabel.textContent = "Signed in account";
  const restore = await fetch("/api/auth/session");
  if (restore.ok) { const session = await restore.json(); csrfToken = session.csrf_token; user = session.user.id; return; }
  document.body.classList.add("auth-screen");
  $("#side").hidden = true;
  $("#view").innerHTML = `<div class="auth-layout">
    <header class="auth-header"><div class="brand"><span class="brand-dot" aria-hidden="true"></span>ORBIT</div><span class="auth-header-note">YOUR TEAM. A NEW ORBIT.</span></header>
    <section class="auth-content" aria-labelledby="login-title">
      <div class="auth-story"><span class="auth-eyebrow">A LITTLE HUMAN DIRECTION.</span><h1>A whole new<br>way to work.</h1><p>Give your agents a purpose.<br>Build a team that goes further.</p><div class="auth-principles"><span>Hire for the job</span><span>Review the work</span><span>Grow their autonomy</span></div></div>
      <div class="auth-card"><span class="auth-eyebrow">WELCOME BACK</span><h2 id="login-title">Your next chapter<br>starts here.</h2><p class="auth-subtitle">Sign in to your team’s workspace.</p>
        <form id="password-login"><label for="login-username">Username</label><input id="login-username" name="username" autocomplete="username" placeholder="Your username" required maxlength="100" autocapitalize="none" spellcheck="false"><label for="login-password">Password</label><div class="pw"><input id="login-password" name="password" type="password" autocomplete="current-password" placeholder="Enter your password" required maxlength="256"><button type="button" class="pw-toggle" id="pw-toggle" aria-pressed="false" aria-controls="login-password">Show</button></div>${config.signup && config.invite_code ? `<div id="invite-row" hidden><label for="login-code">Invite code</label><input id="login-code" name="code" autocomplete="off" placeholder="From the person who invited you" maxlength="100" autocapitalize="none" spellcheck="false"></div>` : ""}<button class="btn primary" type="submit">Enter your workspace ${icon("out")}</button><p id="login-error" role="alert" aria-live="polite"></p></form>
        ${config.signup ? `<p class="auth-help"><span id="auth-switch-text">New here?</span> <button type="button" class="link-btn" id="auth-switch">Create an account</button></p>` : `<p class="auth-help">Need an account? Ask your workspace admin.</p>`}
      </div>
    </section><footer class="auth-footer"><span>Put your team’s potential in motion.</span><span>ORBIT</span></footer>
  </div>`;
  $("#pw-toggle").addEventListener("click", e => { const i = $("#login-password"), show = i.type === "password"; i.type = show ? "text" : "password"; e.currentTarget.textContent = show ? "Hide" : "Show"; e.currentTarget.setAttribute("aria-pressed", String(show)); });
  let creating = false;
  $("#auth-switch")?.addEventListener("click", () => {
    creating = !creating;
    document.querySelector(".auth-card .auth-eyebrow").textContent = creating ? "NEW HERE" : "WELCOME BACK";
    $("#login-title").innerHTML = creating ? "Create your<br>workspace login." : "Your next chapter<br>starts here.";
    document.querySelector(".auth-card .auth-subtitle").textContent = creating ? "Pick a username and a password of 12 or more characters." : "Sign in to your team’s workspace.";
    document.querySelector("#password-login .btn.primary").firstChild.textContent = creating ? "Create account and enter " : "Enter your workspace ";
    $("#login-password").autocomplete = creating ? "new-password" : "current-password";
    $("#login-password").minLength = creating ? 12 : 0;
    const invite = $("#invite-row"); if (invite) invite.hidden = !creating;
    $("#auth-switch-text").textContent = creating ? "Already have one?" : "New here?";
    $("#auth-switch").textContent = creating ? "Sign in" : "Create an account";
    $("#login-error").textContent = "";
  });
  await new Promise(resolve => {
    $("#password-login").addEventListener("submit", async event => {
      event.preventDefault(); const form = event.currentTarget, button = form.querySelector("button[type=submit]"); button.disabled = true;
      try {
        const fields = new FormData(form), payload = { username: fields.get("username"), password: fields.get("password") };
        if (creating && fields.get("code")) payload.code = fields.get("code");
        const response = await fetch(creating ? "/api/auth/signup" : "/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        const session = await response.json();
        if (!response.ok) throw Error(session.error?.message || "Sign-in failed.");
        csrfToken = session.csrf_token; user = session.user.id; form.reset(); document.body.classList.remove("auth-screen"); $("#side").hidden = false; resolve();
      } catch (error) { $("#login-error").textContent = error.message; button.disabled = false; }
    });
  });
}

/* ---------- boot and polling ---------- */
(async () => {
  startSky();
  try { await authenticate(); await load(); authReady = true; if (route().name === "files") loadFiles(); if (!location.hash && S.agents.length) location.replace("#/agent/" + S.agents[0].id); render(); enter(); }
  catch (e) { $("#view").innerHTML = `<div class="center-msg"><h2>Can't reach the server</h2><p class="note">Start it with ./run-arcade.command, then reload.</p></div>`; toast(e.message, true); }
})();

(function poll() {
  const active = S.runs?.some(r => !TERMINAL.includes(r.status));
  setTimeout(async () => {
    const el = document.activeElement, typing = ["INPUT", "TEXTAREA", "SELECT"].includes(el?.tagName) && el.value;
    if (authReady && !busy && !document.hidden && !typing && !$("details.menu[open]") && !["new", "agent"].includes(route().name)) {
      try {
        const snap = () => JSON.stringify([S.runs, S.approvals, S.agents, S.leaderboard, Object.values(S.steps).map(s => s.updated)]);
        const before = snap(); await load();
        if (before !== snap()) { const open = $$("details.quiet[open]").map(d => d.querySelector("summary")?.textContent); ui.stick = innerHeight + scrollY > document.body.scrollHeight - 200; render(); ui.stick = true; $$("details.quiet").forEach(d => { if (open.includes(d.querySelector("summary")?.textContent)) d.setAttribute("open", ""); }); }
      } catch { /* retry next tick */ }
    }
    poll();
  }, route().name === "agent" ? 30000 : active ? 2000 : 6000);
})();
