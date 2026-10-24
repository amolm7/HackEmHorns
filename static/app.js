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
let scoreTab = "approval";

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
function route() { const [name = "arcade", id] = location.hash.replace(/^#\/?/, "").split("/"); return { name, id }; }
function render() {
  const r = route();
  $$("#menu a").forEach(a => { if (a.dataset.route === r.name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  const views = { arcade, hire, queue, scores, shop, agent };
  $("#view").innerHTML = (views[r.name] || arcade)(r.id);
}

/* ---------- screens ---------- */
function rosterCard(a) {
  return `<a class="player" href="#/agent/${esc(a.id)}">${sprite(a.id, a.level, 52)}<h3>${esc(a.name)}</h3><span class="meta">${esc(deptName(a.department_id))} · mgr ${esc(userName(a.manager_id))}</span><span class="row">${lvlChip(a.level)} ${stChip(a.status)}</span></a>`;
}

function arcade() {
  const pending = S.approvals.filter(a => a.status === "pending");
  const top = S.leaderboard.agents.filter(r => r.eligible).slice(0, 3);
  return `<div class="screen">
  <section class="maze"><div class="title-row"><h2>Your AI workforce</h2><a class="btn coin" href="#/hire">Press start · hire</a></div>
    <p class="lede">Describe a job, hire an Intern, review each move it makes, and level it up when it earns your trust.</p></section>
  <div class="split">
    <section class="maze stack"><div class="title-row"><h2>Player select</h2><span class="faint">${S.agents.length} on roster</span></div>
      ${S.agents.length ? `<div class="roster">${S.agents.map(rosterCard).join("")}</div>` : emptyState("No players yet", "Hire your first agent. It starts at level 1 and asks before every action.", `<a class="btn coin" href="#/hire">Insert coin</a>`)}
    </section>
    <div class="stack">
      <section class="maze stack"><div class="title-row"><h2>Queue</h2><a class="btn small" href="#/queue">Open queue</a></div>
        ${pending.length ? pending.slice(0, 3).map(a => `<div class="row between"><span>${esc(agentById(a.agent_id)?.name || "Agent")} wants <b>${esc(a.action.tool_id)}</b></span>${chip("risk-" + a.policy.risk, String(a.policy.risk).toUpperCase())}</div>`).join("<div class=pellets></div>") : `<p class="muted">Nothing waiting. Your agents are idle or running on their own.</p>`}
      </section>
      <section class="maze stack"><div class="title-row"><h2>Top players</h2><a class="btn small" href="#/scores">All scores</a></div>
        ${top.length ? top.map((r, i) => `<div class="row between"><span class="who"><b class="faint">${i + 1}</b>${sprite(r.agent_id, agentById(r.agent_id)?.level, 28)}${esc(r.name)}</span><b>${pct(r.approval_rate)}</b></div>`).join("") : `<p class="muted">Agents enter the board after 5 reviewed actions.</p>`}
      </section>
    </div>
  </div></div>`;
}

function emptyState(title, body, cta = "") {
  return `<div class="empty"><span class="blink">${sprite("empty-" + title, "intern", 56)}</span><h3>${esc(title)}</h3><p>${esc(body)}</p>${cta}</div>`;
}

function hire() {
  const draft = chat.proposal;
  const pendingDrafts = S.proposals.filter(p => p.status === "draft" && p.id !== draft?.id);
  const canHire = S.me.roles.some(r => ["admin", "manager", "builder"].includes(r));
  return `<div class="split">
  <section class="maze stack"><div class="title-row"><h2>Recruiter</h2><button class="btn small" data-act="new-chat">New chat</button></div>
    <p class="muted">Tell the Recruiter what job you need done. It drafts a player card; a manager confirms the hire.</p>
    <div class="chat" id="chat">${chat.log.length ? chat.log.map(m => `<div class="bubble ${m.me ? "me" : "bot"}"><span class="who-line">${m.me ? esc(userName(user)).toUpperCase() : "RECRUITER"}</span>${esc(m.text)}</div>`).join("") : `<div class="bubble bot"><span class="who-line">RECRUITER</span>Ready, player one. What job should your new agent do?</div>`}</div>
    <form class="stack" data-form="recruit">
      <label>JOB<textarea name="message" required>${chat.log.length ? "" : "Hire an agent to triage urgent support tickets and draft replies."}</textarea></label>
      <details ${chat.log.length ? "" : "open"}><summary>Setup</summary><div class="stack">
        <label>NAME<input name="name" value="Ticket Triage" required></label>
        <div class="split"><label>DEPARTMENT<select name="department_id">${deptOpts("support")}</select></label><label>MANAGER<select name="manager_id">${mgrOpts()}</select></label></div>
        <label>MODEL<select name="mode">${modelOpts("demo")}</select><span class="hint">Demo is a labeled deterministic workflow, not an LLM.</span></label>
        <label>UPGRADE AN EXISTING AGENT<select name="target_agent_id"><option value="">No, hire a new agent</option>${S.agents.map(a => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join("")}</select></label>
      </div></details>
      <div class="row"><button class="btn coin" ${canHire ? "" : "disabled"}>Send to Recruiter</button>${canHire ? "" : `<span class="faint">Your role can't hire. Switch player.</span>`}</div>
    </form>
  </section>
  <div class="stack">${draft ? hireCard(draft) : `<section class="maze dim">${emptyState("No card yet", "The Recruiter's draft player card will appear here for review before anyone is hired.")}</section>`}
    ${pendingDrafts.length ? `<section class="maze stack"><h2>Other open cards</h2>${pendingDrafts.map(hireCard).join("")}</section>` : ""}</div>
  </div>`;
}

function hireCard(p) {
  const caps = p.spec.capability_ids.map(id => S.capabilities.find(c => c.id === id)?.name || id);
  const ready = !p.missing_fields.length;
  return `<article class="card-hire"><div class="row between">${sprite(p.id, "intern", 56)}<span class="row">${chip("st-draft", (p.kind === "hire" ? "NEW HIRE" : "UPGRADE") + " · REV " + p.revision)}</span></div>
    <h2>${esc(p.spec.name)}</h2><p>${esc(p.spec.job_description)}</p>
    <div class="stats"><div class="stat"><span>DEPARTMENT</span><b>${esc(deptName(p.spec.department_id))}</b></div><div class="stat"><span>MANAGER</span><b>${esc(userName(p.spec.manager_id))}</b></div><div class="stat"><span>STARTS AT</span><b>LVL 1</b></div></div>
    <div><span class="hud-label">CAPABILITIES</span><div class="row">${caps.map(c => chip("st-active", c)).join("") || '<span class="faint">None</span>'}</div></div>
    <p class="${ready ? "muted" : ""}">${ready ? "Connection checks passed." : "Missing: " + esc(p.missing_fields.join(", ")) + ". Reply in the chat to fill these in."}</p>
    <details><summary>Full review card</summary><pre>${json(p)}</pre></details>
    <div class="row"><button class="btn coin" data-act="confirm" data-id="${esc(p.id)}" data-rev="${p.revision}" ${ready ? "" : "disabled"}>${p.kind === "hire" ? "Confirm hire" : "Confirm upgrade"}</button><span class="faint">Only the assigned manager or an admin can confirm.</span></div>
  </article>`;
}

function queue() {
  const pending = S.approvals.filter(a => a.status === "pending");
  const past = S.approvals.filter(a => a.status !== "pending");
  return `<div class="screen"><section class="maze"><div class="title-row"><h2>Approval queue</h2><span class="faint">${pending.length} waiting</span></div>
    <p class="lede">Level 1 agents freeze before every move. Approve the exact arguments, send it back with notes, or stop it.</p></section>
  ${pending.length ? `<div class="stack">${pending.map(quest).join("")}</div>` : `<section class="maze dim">${emptyState("Queue clear", "No moves are waiting for you. Start a run from an agent's page to see one here.")}</section>`}
  ${past.length ? `<section class="maze stack"><h2>History</h2>${past.slice().reverse().slice(0, 20).map(a => `<div class="row between"><span>${esc(agentById(a.agent_id)?.name || "Agent")} · ${esc(a.action.tool_id)}</span>${stChip(a.status)}</div>`).join("<div class=pellets></div>")}</section>` : ""}</div>`;
}

function quest(a) {
  const ag = agentById(a.agent_id);
  const mine = a.assigned_manager_id === user || S.me.roles.includes("admin");
  return `<article class="quest pending"><div class="row between"><span class="who">${sprite(a.agent_id, ag?.level, 36)}<span><h3>${esc(ag?.name || "Agent")}</h3><span class="faint">wants to run <b>${esc(a.action.tool_id)}</b></span></span></span>${chip("risk-" + a.policy.risk, String(a.policy.risk).replace(/_/g, " ").toUpperCase())}</div>
    <p class="muted">${esc(a.policy.reason)}</p>
    <pre class="args">${json(a.action.arguments)}</pre>
    <details><summary>Action snapshot and evidence</summary><pre data-evidence="${esc(a.id)}">${json(a)}</pre></details>
    <form class="stack" data-form="decide" data-id="${esc(a.id)}">
      <label>NOTES<input name="comment" placeholder="Required if you send it back"></label>
      <div class="row"><button class="btn ok" name="decision" value="approve" ${mine ? "" : "disabled"}>Approve</button><button class="btn warn" name="decision" value="request_revision" ${mine ? "" : "disabled"}>Send back</button><button class="btn bad" name="decision" value="reject" ${mine ? "" : "disabled"}>Reject</button>
      ${mine ? "" : `<span class="faint">Assigned to ${esc(userName(a.assigned_manager_id))}.</span>`}</div>
    </form></article>`;
}

function scores() {
  const lb = S.leaderboard;
  const elig = lb.agents.filter(r => r.eligible), champ = elig[0];
  const tabs = [["approval", "Approval rate"], ["reuse", "Most reused"], ["creators", "Top creators"]];
  let table = "";
  if (scoreTab === "approval") {
    table = lb.agents.length ? `<table class="scores"><thead><tr><th>RANK</th><th>PLAYER</th><th class="num hide-sm">REVIEWS</th><th class="num">SCORE</th></tr></thead><tbody>${lb.agents.map((r, i) => `<tr><td class="rank">${r.eligible ? String(i + 1).padStart(2, "0") : "--"}</td><td><a class="who" href="#/agent/${esc(r.agent_id)}">${sprite(r.agent_id, agentById(r.agent_id)?.level, 30)}${esc(r.name)}</a></td><td class="num hide-sm">${r.reviewed_actions}</td><td class="score ${r.eligible ? "" : "locked"}">${r.eligible ? pct(r.approval_rate) : `${r.reviewed_actions}/${lb.minimum_reviewed_actions} TO RANK`}</td></tr>`).join("")}</tbody></table>` : emptyState("Board empty", "Hire agents and review their actions to fill the board.");
  } else if (scoreTab === "reuse") {
    table = lb.capability_reuse.length ? `<table class="scores"><thead><tr><th>RANK</th><th>CAPABILITY</th><th class="hide-sm">CREATOR</th><th class="num">INSTALLS</th></tr></thead><tbody>${lb.capability_reuse.map((r, i) => `<tr><td class="rank">${String(i + 1).padStart(2, "0")}</td><td>${esc(S.capabilities.find(c => c.id === r.capability_id)?.name || r.capability_id)}</td><td class="hide-sm">${esc(userName(r.creator_id))}</td><td class="score">${r.installations}</td></tr>`).join("")}</tbody></table>` : emptyState("No reuse yet", "Publish a cartridge in the shop and install it to score reuse.");
  } else {
    table = lb.creator_reuse.length ? `<table class="scores"><thead><tr><th>RANK</th><th>CREATOR</th><th class="num">INSTALLS OF THEIR WORK</th></tr></thead><tbody>${lb.creator_reuse.map((r, i) => `<tr><td class="rank">${String(i + 1).padStart(2, "0")}</td><td>${esc(userName(r.creator_id))}</td><td class="score">${r.installations}</td></tr>`).join("")}</tbody></table>` : emptyState("No creators yet", "Creators score when someone installs what they built.");
  }
  return `<div class="screen">
  ${champ ? `<section class="champ">${sprite(champ.agent_id, agentById(champ.agent_id)?.level, 72)}<div><span class="hud-label">PLAYER OF THE MONTH</span><h2>${esc(champ.name)}</h2><p class="muted">${champ.reviewed_actions} reviewed actions</p></div><span class="big">${pct(champ.approval_rate)}</span></section>` : ""}
  <section class="maze stack"><div class="title-row"><h2>High scores</h2><div class="tabs" role="group" aria-label="Ranking">${tabs.map(([k, t]) => `<button data-act="tab" data-tab="${k}" aria-pressed="${scoreTab === k}">${t}</button>`).join("")}</div></div>
    ${table}
    <p class="faint">Scores come from real manager reviews and installs. Players rank after ${lb.minimum_reviewed_actions} reviewed actions.</p></section></div>`;
}

function shop() {
  return `<div class="split">
  <section class="maze stack"><div class="title-row"><h2>Cartridges</h2><span class="faint">${S.capabilities.length} in catalog</span></div>
    <p class="muted">Capabilities your company set up once. Any allowed agent can plug them in.</p>
    ${S.capabilities.map(c => `<article class="quest"><div class="row between"><h3>${esc(c.name)}</h3><span class="faint">v${c.version} · by ${esc(userName(c.creator_id))}</span></div><p class="muted">${esc(c.description)}</p><div class="row">${c.tool_contracts.map(t => chip("risk-" + t.risk, `${t.name} · ${String(t.risk).replace(/_/g, " ")}`)).join("")}</div><div class="row"><button class="btn small" data-act="publish" data-kind="capability" data-id="${esc(c.id)}">Publish to shop</button></div></article>`).join("")}
    <form class="row" data-form="publish-agent"><label>PUBLISH AN AGENT TEMPLATE<select name="source_id">${S.agents.map(a => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join("")}</select></label><button class="btn" ${S.agents.length ? "" : "disabled"}>Publish</button></form>
  </section>
  <section class="maze stack"><div class="title-row"><h2>Company shop</h2><span class="faint">${S.marketplace.length} listings</span></div>
    <p class="muted">Installs carry no credentials, connections, or earned trust. New agents start at level 1.</p>
    ${S.marketplace.length ? S.marketplace.map(l => `<article class="quest"><div class="row between"><h3>${esc(l.payload.name)}</h3>${chip("st-active", l.kind.toUpperCase())}</div><p class="faint">by ${esc(userName(l.creator_id || l.publisher_id))} · ${l.installation_count} installs</p>
      <details><summary>Nutrition label</summary><pre>${json(l)}</pre></details>
      <form class="stack" data-form="install" data-id="${esc(l.id)}">${l.kind === "agent" ? `<div class="split"><label>DEPARTMENT<select name="department_id">${deptOpts("support")}</select></label><label>MANAGER<select name="manager_id">${mgrOpts()}</select></label></div>` : ""}<div class="row"><button class="btn coin small">Install</button></div></form></article>`).join("") : emptyState("Shop empty", "Publish a cartridge or agent template to stock the shop.")}
  </section></div>`;
}

function agent(id) {
  const a = agentById(id);
  if (!a) return `<section class="maze">${emptyState("Player not found", "This agent isn't visible to the current player.", `<a class="btn" href="#/arcade">Back to arcade</a>`)}</section>`;
  const runs = S.runs.filter(r => r.agent_id === a.id).slice().reverse();
  const lb = S.leaderboard.agents.find(r => r.agent_id === a.id);
  const reviews = lb?.reviewed_actions || 0, need = S.leaderboard.minimum_reviewed_actions;
  const manages = a.manager_id === user || S.me.roles.includes("admin");
  return `<div class="screen">
  <section class="maze stack"><div class="row between"><span class="who">${sprite(a.id, a.level, 84)}<span class="stack"><h2>${esc(a.name)}</h2><span class="row">${lvlChip(a.level)} ${stChip(a.status)}</span></span></span><a class="btn small" href="#/arcade">Back</a></div>
    <p class="lede">${esc(a.job_description)}</p>
    <div class="stats"><div class="stat"><span>DEPARTMENT</span><b>${esc(deptName(a.department_id))}</b></div><div class="stat"><span>MANAGER</span><b>${esc(userName(a.manager_id))}</b></div><div class="stat"><span>SPEC</span><b>v${a.spec_version}</b></div><div class="stat"><span>APPROVAL</span><b>${lb?.eligible ? pct(lb.approval_rate) : "--"}</b></div></div>
    <div class="stack"><span class="hud-label">REVIEWS TOWARD RANKING · ${Math.min(reviews, need)}/${need}</span><div class="xp"><i data-xp="${Math.min(1, reviews / need)}"></i></div></div>
  </section>
  <div class="split">
    <div class="stack">
      ${a.status !== "active" ? `<section class="maze stack"><h2>Plug in</h2><p class="muted">Validate this agent's local connections to activate it.</p><button class="btn coin" data-act="activate" data-id="${esc(a.id)}" ${manages ? "" : "disabled"}>Validate and activate</button></section>` : ""}
      <section class="maze stack"><h2>New run</h2><form class="stack" data-form="run" data-id="${esc(a.id)}"><label>TASK<textarea name="task">Triage the urgent login outage and draft a reply.</textarea></label><label>MODEL<select name="mode">${modelOpts(a.model_profile_id || "demo")}</select></label><div class="row"><button class="btn coin" ${a.status === "active" ? "" : "disabled"}>Start run</button>${a.status === "active" ? "" : `<span class="faint">Activate first.</span>`}</div></form></section>
      <section class="maze stack"><h2>Level</h2><p class="muted">Level 2 lets reads run alone. Drafts always need you.</p>
        <form class="stack" data-form="level" data-id="${esc(a.id)}"><label>REASON<input name="reason" value="Reviewed its work and scoped permissions." required></label>
        <div class="row">${a.level === "intern" ? `<button class="btn coin" name="level" value="associate" ${manages ? "" : "disabled"}>Level up</button>` : `<button class="btn warn" name="level" value="intern" ${manages ? "" : "disabled"}>Drop to level 1</button>`}</div></form></section>
      <section class="maze stack"><h2>Stats</h2><button class="btn small" data-act="perf" data-id="${esc(a.id)}">Load stats and versions</button><div id="perf"></div></section>
    </div>
    <section class="maze stack"><div class="title-row"><h2>Runs</h2><span class="faint">${runs.length}</span></div>
      ${runs.length ? runs.map(r => `<article class="quest"><div class="row between">${stChip(r.status)}<span class="faint">${esc(r.mode)}</span></div><p>${esc(r.task)}</p>${r.error ? `<p class="st-failed">${esc(r.error)}</p>` : ""}${r.result ? `<pre class="args">${esc(typeof r.result === "string" ? r.result : JSON.stringify(r.result, null, 2))}</pre>` : ""}
        <div class="row"><button class="btn small" data-act="replay" data-id="${esc(r.id)}">Replay</button>${r.status === "awaiting_approval" ? `<a class="btn small warn" href="#/queue">Review in queue</a>` : ""}${!TERMINAL.includes(r.status) ? `<button class="btn small bad" data-act="cancel" data-id="${esc(r.id)}">Cancel</button>` : ""}${["completed", "failed"].includes(r.status) && manages ? `<button class="btn small ok" data-act="outcome" data-id="${esc(r.id)}" data-ok="true">Task passed</button><button class="btn small bad" data-act="outcome" data-id="${esc(r.id)}" data-ok="false">Task failed</button>` : ""}</div>
        <div data-replay="${esc(r.id)}"></div></article>`).join("") : emptyState("No runs yet", a.status === "active" ? "Start a run. At level 1 it will pause before its first tool call." : "Activate this agent, then start a run.")}
    </section>
  </div></div>`;
}

/* ---------- events (delegated; CSP forbids inline handlers) ---------- */
document.addEventListener("click", e => {
  const b = e.target.closest("[data-act]"); if (!b) return;
  const { act: kind, id } = b.dataset;
  if (kind === "new-chat") { chat = { id: null, log: [], proposal: null }; render(); }
  if (kind === "tab") { scoreTab = b.dataset.tab; render(); }
  if (kind === "confirm") act(async () => { const a = await api(`recruiter/proposals/${id}/confirm`, "POST", { revision: Number(b.dataset.rev) }); chat = { id: null, log: [], proposal: null }; location.hash = "#/agent/" + a.id; return `${a.name} joined the roster at level 1.`; }, b);
  if (kind === "publish") act(async () => { await api("marketplace", "POST", { kind: b.dataset.kind, source_id: id }); return "Published to the company shop."; }, b);
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
    try { const [p, v] = await Promise.all([api(`agents/${id}/performance`), api(`agents/${id}/versions`)]);
      $("#perf").innerHTML = `<div class="stats"><div class="stat"><span>REVIEWED</span><b>${p.reviewed_actions}</b></div><div class="stat"><span>APPROVED</span><b>${p.approved_actions}</b></div><div class="stat"><span>SENT BACK</span><b>${p.revision_requests}</b></div><div class="stat"><span>REJECTED</span><b>${p.rejected_actions}</b></div><div class="stat"><span>RUNS DONE</span><b>${p.completed_runs}/${p.run_count}</b></div><div class="stat"><span>TASKS PASSED</span><b>${p.successful_tasks}/${p.evaluated_tasks}</b></div></div><details><summary>${v.length} spec versions</summary><pre>${json(v)}</pre></details>`; }
    catch (err) { toast(err.message, true); }
  })();
});

document.addEventListener("submit", e => {
  const f = e.target, kind = f.dataset.form; if (!kind) return; e.preventDefault();
  const d = Object.fromEntries(new FormData(f)), sub = e.submitter;
  if (sub?.name) d[sub.name] = sub.value;
  if (kind === "recruit") act(async () => {
    if (!d.target_agent_id) delete d.target_agent_id;
    d.connection_id = "support-local"; d.model_profile_id = d.mode;
    if (!chat.id) chat.id = (await api("recruiter/conversations", "POST", {})).id;
    chat.log.push({ me: true, text: d.message });
    try { const r = await api(`recruiter/conversations/${chat.id}/messages`, "POST", d); chat.proposal = r.proposal; chat.log.push({ me: false, text: r.message }); }
    catch (err) { chat.log.push({ me: false, text: "Couldn't draft that: " + err.message }); throw err; }
  }, sub);
  if (kind === "decide") {
    if (d.decision === "request_revision" && !d.comment.trim()) { toast("Add notes so the agent knows what to change.", true); f.comment.focus(); return; }
    act(async () => { await api(`approvals/${f.dataset.id}/decision`, "POST", d); return { approve: "Approved. The agent continues.", reject: "Rejected. That move won't run.", request_revision: "Sent back with your notes." }[d.decision]; }, sub);
  }
  if (kind === "run") act(async () => { await api(`agents/${f.dataset.id}/runs`, "POST", { task: d.task, mode: d.mode, max_steps: 8 }); return "Run started. Level 1 moves will land in your queue."; }, sub);
  if (kind === "level") act(async () => { const a = agentById(f.dataset.id); await api(`agents/${a.id}/level`, "POST", { level: d.level, reason: d.reason }); if (d.level !== "intern") levelUp(a.name, d.level); return d.level === "intern" ? `${a.name} dropped to level 1.` : null; }, sub);
  if (kind === "publish-agent") act(async () => { await api("marketplace", "POST", { kind: "agent", source_id: d.source_id }); return "Template published. No connections or trust included."; }, sub);
  if (kind === "install") act(async () => { const r = await api(`marketplace/${f.dataset.id}/install`, "POST", d.department_id ? d : {}); if (r.resource?.level) location.hash = "#/agent/" + r.resource.id; return "Installed. It starts at level 1 and needs local connections."; }, sub);
});

$("#identity").addEventListener("change", e => { user = e.target.value; sessionStorage.setItem("dev-user", user); chat = { id: null, log: [], proposal: null }; act(async () => `Now playing as ${userName(user)}.`); });
addEventListener("hashchange", () => { render(); scrollTo({ top: 0 }); });

// XP bars animate via transform once rendered (CSSOM, allowed by CSP).
new MutationObserver(() => $$("[data-xp]").forEach(i => { i.style.transform = `scaleX(${i.dataset.xp})`; })).observe($("#view"), { childList: true });

(async () => { try { await load(); render(); } catch (e) { $("#view").innerHTML = `<section class="maze">${emptyState("Cabinet offline", "Start the server with python server.py, then reload.")}</section>`; toast(e.message, true); } })();

// Light polling so queue and runs stay live; skip while the player is typing or reading a trace.
setInterval(async () => {
  if (busy || document.hidden || !["arcade", "queue", "agent"].includes(route().name)) return;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) || $$("details[open]").length || $$("[data-replay] *").length) return;
  try { const before = JSON.stringify([S.runs, S.approvals, S.agents]); await load(); if (before !== JSON.stringify([S.runs, S.approvals, S.agents])) render(); } catch {}
}, 2500);
