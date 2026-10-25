# Engineering backlog and investigation handoff

**Review date:** October 25, 2026. **Branch:** `fix/library-custom-tools`.

This review covers the current working tree, including the uncommitted GitHub integration and manager-permission changes. The last committed revision at review time was `b4f0551`; checking out that revision alone will not reproduce this implementation. See ISS-012 before handing this work to someone on another computer.

**Handoff update:** the implementation and this backlog were committed as `fca2311` on `fix/library-custom-tools`. The feature branch includes `origin/main` at `b6b38bc` as its integration baseline. ISS-012's missing-file/commit prerequisite is addressed by that commit; the issue descriptions below retain the original scan baseline.

The request was to investigate and prepare a backlog. These tickets describe open work, not fixes implemented by this review. Do not mark a ticket complete because the existing tests pass.

## Findings that matter first

The reported **“Maximum tool calls reached”** failure has a concrete cause:

- Saved run: `43882f20-41e9-4900-906a-4e7fa447bae3`.
- Created: `2026-10-25T06:06:49.875769+00:00`.
- Model profile: `meta`; configured tool budget: **8**; model turns: **4**.
- Executed: **8 `github_read_file` actions**, with **8 distinct argument sets**. This run was not an identical-call loop.
- Remaining queue: **`create_slideshow`**. The ninth call would have saved the requested deliverable.
- The agent had **both GitHub reading and slideshow capabilities**. Missing permissions or a missing Slides capability did not explain this failure.
- Terminal error: `step_limit`. No slideshow tool executed in that run.

Two additional bugs were reproduced in an isolated temporary database:

1. Sending another message in a conversation whose last run failed or was cancelled returns **409 `invalid_request`**, saying to wait for a task that has already stopped.
2. A model response claiming “I saved the slideshow” can complete a normal chat run with **zero artifact tool executions**.

A third probe confirmed that submitting an identical workspace-bundle creation request twice with the **same idempotency key** creates **different capability records**.

## Scan evidence and limits

| Check | Result |
| --- | --- |
| Full backend regression suite | **155 tests passed**, 76.892 seconds in this scan. |
| Frontend syntax | `node --check static/app.js` passed. |
| Frontend contracts | `node tests/test_frontend_contracts.js` passed. These are VM/string/behavior checks, not browser automation. |
| Patch whitespace | `git diff --check` passed. |
| Runtime dependency advisory scan | `pip-audit -r requirements.txt` reported **no known vulnerabilities** for the resolved dependencies. |
| Credential-pattern scan | **0 matches** in tracked and non-ignored untracked files for the checked GitHub/Muse/Google/private-key patterns. This is not a complete Git history or secret-management audit. |
| Local secret-file handling | `.env` is Git-ignored and mode **0600**. No credential values are included here. |
| Saved application runs | At the time of inspection: **6 total**, **5 completed**, **1 failed**. The failed run had `step_limit`. Completion is not proof of output quality. |
| Additional probes | Temporary databases and mocked model responses; no changes to saved production/demo runs. |

No new paid model calls, live GitHub reads, load tests, independent penetration test, or browser visual/accessibility test were performed for this backlog. Earlier live GitHub checks succeeded against a public repository; they do not establish access to every repository or ongoing credential validity.

## Priority and evidence conventions

- **P0:** protect credentials before external sharing; requires a credential owner.
- **P1:** demo reliability, blocked workflows, misleading results, or a release prerequisite. Address first.
- **P2:** correctness/usability gaps or prerequisites for broader deployment.
- **Observed:** supported by a saved application run or an isolated reproduction.
- **Code-confirmed:** a specific current code path establishes the behavior, but the full user scenario was not exercised live.
- **Design limitation:** intentional/bounded prototype behavior that needs a product or deployment decision; not an allegation of an exploited vulnerability.

All tickets below are **open** except the commit/package prerequisite in ISS-012, addressed in the handoff update above. Suggested owners identify engineering responsibilities, not assignments to specific teammates.

## Backlog index

| ID | Priority | Issue | Evidence | Suggested owner |
| --- | --- | --- | --- | --- |
| ISS-001 | P1 | Reading exhausts the tool budget before saving deliverables | Observed saved run | Runtime + frontend |
| ISS-002 | P1 | Failed/cancelled conversations cannot accept an ordinary retry | Reproduced | Runtime + frontend |
| ISS-003 | P1 | Normal chat can claim a deliverable was saved without creating it | Reproduced | Runtime + quality |
| ISS-004 | P1 | Recruiter prompt incorrectly says GitHub is not connected | Code-confirmed | Recruiter |
| ISS-005 | P1 | Errors lose codes, field details, and recovery actions in the UI | Code-confirmed | API + frontend |
| ISS-006 | P1 | Transient GitHub failures are never retried by the worker | Code-confirmed | Integrations + runtime |
| ISS-007 | P1 | A recoverable GitHub path error can terminate the entire task | Code-confirmed | Integrations + runtime |
| ISS-008 | P1 | GitHub can be attached to a Demo agent that cannot run it | Code-confirmed/test-covered limitation | Recruiter + frontend |
| ISS-009 | P1 | GitHub results can make follow-ups exceed the history limit | Code-confirmed | Runtime + model adapters |
| ISS-010 | P1 | Connection-recovery messages point to removed Library setup | Code-confirmed | Integrations + frontend + docs |
| ISS-011 | P0 | Rotate credentials previously shared in the conversation | Observed exposure; manual work | Credential owners |
| ISS-012 | P1 | Feature implementation is not fully committed for teammate handoff | Observed Git state | Feature owner |
| ISS-013 | P2 | Department dropdown can offer departments the manager cannot use | Code-confirmed | Integrations + frontend |
| ISS-014 | P2 | “Connected” reflects stored configuration, not current live health | Design limitation | Integrations + frontend |
| ISS-015 | P2 | Workspace bundle creation ignores idempotency keys | Reproduced | API + registry |
| ISS-016 | P2 | Workspace bundle descriptions are mostly metadata, unlike GitHub skills | Code-confirmed | Registry + runtime |
| ISS-017 | P2 | GitHub pagination, truncation and revision identity are incomplete | Design limitation | Integrations |
| ISS-018 | P2 | Recruiter model calls hold SQLite write transactions | Code-confirmed | Backend/platform |
| ISS-019 | P2 | Activity streams and list endpoints repeatedly scan unbounded history | Code-confirmed scalability gap | Backend/platform |
| ISS-020 | P2 | HTTP internal-error diagnostics lack sufficient correlation | Code-confirmed | Backend/platform |
| ISS-021 | P2, before private enterprise use | Shared-token repository access is coarser than department authorization | Design limitation | Security/platform |
| ISS-022 | P2 | Skill instructions are not consistently tied to immutable versions | Design limitation | Registry + runtime |
| ISS-023 | P2 | Tests miss realistic exploration and browser workflows | Confirmed coverage gap | QA + feature owners |
| ISS-024 | P2 | Older docs still describe superseded approval/integration behavior | Code/document comparison | Feature owners |

## ISS-001 — Reserve tool budget for actual deliverables

**Evidence:** the saved failure above. **Files:** [static/app.js](../static/app.js), `run` form handler (around line 651); [backend/runtime/__init__.py](../backend/runtime/__init__.py), `start`, model prompt construction, action creation (around lines 273, 719, 815); [backend/api/schemas.py](../backend/api/schemas.py), `RunCreate`.

**Current behavior:** chat always sends `max_steps: 8`; backend accepts 1–20. The limit counts executed tool actions, not model turns. Eight distinct reads can exhaust it before a queued artifact write. The model receives skill instructions but no reliable remaining-call budget or deliverable reservation. Parallel function calls can consume several calls in one turn. A larger number alone does not solve unbounded exploration.

**Reproduce:** use a GitHub + Slides agent; mock successive model responses requesting eight distinct file reads followed by `create_slideshow`. The ninth action fails before dispatch. The saved run provides a real example without new API spend.

**Proposed implementation:**

1. Define a server-owned bounded budget policy and expose an optional advanced UI budget. Keep a hard server ceiling; do not accept arbitrary huge values.
2. Persist the task's intended deliverables explicitly. Reserve enough calls for the requested local artifacts; a Slides + Documents task may need two output slots.
3. Add remaining calls, completed reads, outstanding artifacts and a stop-research instruction to model context before every planning turn.
4. Reject or trim an over-budget proposed batch before performing it, with a bounded opportunity to plan the output from existing evidence. Do not simply execute unauthorized replacement actions.
5. Show progress such as “6 of 8 calls used; preparing slides.” Detect identical-read loops separately; they did not cause the observed failure.

**Acceptance:** with a budget of eight, a bounded GitHub-to-slides scenario saves a deck within eight executed actions; large batches cannot overrun the cap; requests for unsupported budgets are rejected; partial evidence is disclosed; no infinite retries or hidden budget increases. Preserve action approvals, scopes and deduplication. Add deterministic tests for parallel reads, multiple deliverables, exact-boundary completion and research-only tasks.

## ISS-002 — Recover from failed or cancelled conversations

**Evidence:** isolated probes for both terminal states returned 409 `invalid_request`: “Wait for the previous task to finish, or start a new conversation.” **Files:** [backend/runtime/conversations.py](../backend/runtime/conversations.py), `attach`, lines 40–48; [static/app.js](../static/app.js), `followTarget` and run submission.

The frontend sends the active `conversation_id` even when `followTarget` declines to select a failed run. `attach` still resolves that conversation's `last_run_id` and requires it to be `completed`. There is no “finish waiting” transition for a failed/cancelled task.

**Reproduce:** create a run in a temporary database, set it to failed, then POST another task with the same `conversation_id`. Repeat with cancelled. No live model is needed.

**Proposed fix:** distinguish an in-flight previous run from a terminal failure. Offer **Retry as a new attempt** and **New conversation** explicitly. Decide whether retry reuses a compact evidence checkpoint or starts fresh; do not silently replay executed writes. Record `retry_of`/lineage if introduced. A recovery path must recheck current actor, agent version, connection, repository and policy.

**Acceptance:** failed/cancelled threads display useful next actions; retry creates exactly one new run; active threads still reject overlapping messages; wrong-user/stale-conversation/repository-switch protections remain intact. An unchanged GitHub read may be reused only under a documented, permission-checked cache policy.

## ISS-003 — Verify requested artifacts before claiming completion

**Evidence:** a temporary Slides agent with a mocked final answer “I saved the slideshow” completed with **zero tool steps**. **Files:** [backend/quality.py](../backend/quality.py), `check` returns `None` without `work_item_id`; [backend/runtime/__init__.py](../backend/runtime/__init__.py), `finish`; [static/app.js](../static/app.js), `agentTurn`.

Team work has structural deliverable checks. Ordinary agent chat does not inherit them, although the demo happens in chat. A final model sentence is currently sufficient to mark an artifact request completed.

**Proposed fix:** introduce a small task output contract for chat, e.g. `requested_artifacts: ["slideshow"]`, confirmed by the user/UI or derived by a bounded proposal step. Verify saved artifacts from executed actions, not from model prose. A missing artifact can trigger one budget-aware repair, then a clear incomplete/failure result. Keep genuine reading/question-answering tasks able to finish without an artifact.

**Acceptance:** fake saved-deck claims do not pass; an actual saved slideshow does; Slides + Document verifies both; asking a repository question does not force an unwanted deck; validation does not equate structural success with factual accuracy. Coordinate with ISS-001 so repair does not require calls that have already been exhausted.

## ISS-004 — Remove contradictory GitHub setup instructions

**Evidence:** [backend/recruiter/__init__.py](../backend/recruiter/__init__.py), `message`, around line 206, still tells the setup model: **“No GitHub, email sending or other external integrations are connected.”** The same request can contain the published GitHub capability. `quick_create` uses a live setup model when a description and a live profile are supplied.

**Impact:** the helper can produce instructions that decline GitHub work even though selection and backend validation permit it. This is a confirmed prompt contradiction; it is not proven to have caused the saved tool-budget failure.

**Proposed fix:** build a capability/connection-aware setup context. State that GitHub reading is available only when published and authorized, while sending email and GitHub writes remain unavailable. Keep explicit selected capability IDs authoritative. Do not make a generic model promise that an unprepared connector exists.

**Acceptance:** capture the helper prompt in mocked tests for connected GitHub + Slides, disconnected GitHub, plain Slides, and an inaccessible department. No prompt says GitHub is disconnected when it is actually authorized. No unselected tool or credential is invented.

## ISS-005 — Preserve structured errors and show recovery actions

**Evidence:** [static/app.js](../static/app.js), `api` around line 68 creates `Error(message)` and discards `error.code`, `error.details`, HTTP status and request ID. `narrate` shows a plain failed-run string. Several backend limits still use generic `invalid_request`.

**Proposed fix:** add a typed frontend error carrying safe status/code/details/request ID. Give stable backend codes to distinct limits. Render inline field errors for 422s and contextual recovery for run failures. Keep a generic fallback for unknown errors. Do not show raw provider responses, token values, stack traces or submitted passwords.

| Current code/condition | Desired user action |
| --- | --- |
| `step_limit` | Show calls used and preserved work; start a bounded new attempt. |
| `github_error` | Use the classified cause from ISS-006/007, not a universal retry. |
| `github_not_configured`, stale credential binding | Explain that an admin must prepare/retest the connector. |
| `connection_denied` | Explain department/access or revoked connection; do not offer a bypass. |
| `repository_changed` | Offer a new conversation while preserving the drafted task/repository. |
| `github_requires_live_model` | Explain model compatibility and a reviewed migration/recreation path. |
| `token_budget` / long history | Start a new conversation or use an authorized compact checkpoint. |
| `provider_error`, `retry_exhausted` | Distinguish scheduled retry, exhausted retry and permanent configuration failure. |
| `deliverable_validation` | Show missing/failed outputs and preserve completed artifacts. |
| `internal_error` | Show a support/request ID and a safe message. |

**Acceptance:** errors are distinguishable without parsing English strings; form values survive failures; keyboard focus reaches the error; role restrictions are clear; diagnostic IDs match server records; frontend tests cover each branch and unknown-code fallback.

## ISS-006 — Retry transient GitHub reads safely

**Evidence:** [backend/github.py](../backend/github.py), `_session`, maps HTTP/network failures to `github_error` without retry metadata or retained `Retry-After`. [backend/runtime/__init__.py](../backend/runtime/__init__.py), `advance_safely`, retries only `provider_error` with `details.retryable`.

**Impact:** a temporary GitHub timeout, rate limit or service failure ends the run even though the operation is read-only. No such failure was found in the six saved runs; this is a confirmed code-path gap.

**Proposed fix:** use sanitized categories and retry metadata for GitHub network failures, 408/429/appropriate 5xx responses. Some 403s are rate limits and others are permanent authorization failures; classify conservatively using safe status/header information. Honor bounded `Retry-After`, backoff, jitter, cancellation and maximum attempts. Decide whether counters are per action or per run; the existing model retry count is cumulative.

**Acceptance:** fake 429 then success resumes the same read without creating a duplicate artifact; timeout retries are bounded; permanent 401/403/404 do not spin; exhausted retries retain useful evidence; cancellation during backoff works; credentials never appear in messages or logs.

## ISS-007 — Let the model recover from missing repository paths

**Evidence:** `GitHubMCP.call` turns any MCP `isError` response into a fatal `Error`. A nonexistent guessed README path is treated similarly to an inaccessible repository. The web reader already has a different, recoverable `page_error` pattern.

**Proposed fix:** separate connection/auth/repository failures from a missing selected path or an unsupported file representation. Return a sanitized structured tool error for a recoverable path miss, allowing one directory lookup or a corrected path. Keep access denials fatal and do not forward arbitrary upstream instructions as trusted errors. If the upstream message cannot be classified safely, fail clearly rather than guessing.

**Acceptance:** a misspelled file followed by a directory listing and valid file can still produce the artifact; the agent does not retry the same missing path indefinitely; permission failures cannot be converted into a successful read; retries consume a documented bounded budget.

## ISS-008 — Prevent incompatible GitHub + Demo configurations

**Evidence:** GitHub task start rejects Demo mode (`github_requires_live_model`), but agent creation can produce this combination. The frontend's `createAgent` returns early for an existing target agent before the new-agent Demo compatibility check. Thus adding GitHub to an existing Demo agent can succeed and make every subsequent task fail. The existing GitHub tests demonstrate that such a Demo agent can be created and then rejected at run time.

**Files:** [static/app.js](../static/app.js), `createAgent`, lines 561–566; [backend/recruiter/__init__.py](../backend/recruiter/__init__.py), create/add/patch paths; [backend/runtime/__init__.py](../backend/runtime/__init__.py), `start`.

**Proposed fix:** enforce connector/model compatibility server-side on create, capability addition, patch and template activation. Validate before committing a new version. Offer a clearly reviewed model change or creation of a compatible new agent; do not silently switch providers or change credentials. Mirror the rule in the UI.

**Acceptance:** adding GitHub to a Demo agent fails without changing its bindings/version; a live-model agent succeeds; raw API calls cannot bypass the check; template installation has a meaningful needs-configuration state; existing invalid agents have a documented recovery path.

## ISS-009 — Bound and compact input history, not only output tokens

**Evidence:** GitHub results allow up to 30,000 text characters per call. [backend/runtime/__init__.py](../backend/runtime/__init__.py), `start`, rejects follow-ups when serialized previous `contents` reaches 60,000 characters. A few substantial file reads can exceed this. During an individual run, tool responses accumulate without an equivalent input-context budget. Output usage is checked before a model call, so a response can also cross the configured output threshold before the next check.

**Proposed fix:** define per-result, per-turn and per-conversation input budgets using provider-appropriate token estimation. Store full evidence separately and place bounded, provenance-preserving excerpts/summaries in model context. Preserve matching tool-call/result IDs for Meta/Gemini; dropping arbitrary messages breaks protocol history. Limit new output to the remaining budget where supported. Explain when compaction prevents a full repository audit.

**Acceptance:** multiple long reads can lead to a useful bounded follow-up; exact 60k boundary tests are deterministic; a malicious/huge tool result cannot explode input context; compacted claims retain source references; permission revocation still blocks reuse; byte/character/token limits are explicitly distinguished. No claim of a hard dollar budget unless one is actually enforced.

## ISS-010 — Fix the removed connector recovery destination

**Evidence:** GitHub errors in runtime/validation still instruct users to **“Reconnect from Library”**. Connection preparation was intentionally moved out of Library into [scripts/prepare_github.py](../scripts/prepare_github.py). The bottom form publishes a tool; it cannot refresh a credential fingerprint or prepare the connector.

**Proposed fix:** for the hackathon, give a role-aware message pointing to the admin/pre-demo preparation step and preserve the user's task. Longer term, add an actual admin connector settings/retest screen, separate from tool creation. Do not make managers re-enter token values in a Library skill form.

**Acceptance:** change a test credential, trigger the stale-binding error, and follow the displayed instructions successfully. A manager sees who must act; an admin sees the exact available preparation mechanism. Retesting a connection does not create duplicate Library tools or transfer trust.

## ISS-011 — Rotate exposed credentials

**Evidence:** provider and GitHub credentials were supplied in the conversation. Ignoring `.env` protects source control but does not revoke credentials already shared elsewhere. No credential values are reproduced here, and the source scan found no checked patterns in versionable files.

**Owner/action:** each credential owner must revoke the old value at its provider, create a replacement with minimum required access, update the local/server secret store, and verify it. The coding agent cannot infer provider-account authorization or prove that all copies have been erased.

**Acceptance:** old tokens are revoked; new values remain outside Git; GitHub is prepared again with the replacement; a permitted repository works and a prohibited private repository does not; model checks are run with approved test data. Do not paste replacement credentials into issues, PRs, this backlog, logs or chat. Maintain an incident/rotation record without the secrets themselves.

## ISS-012 — Make the working tree available to the next teammate

**Evidence:** `git status` shows modified files and untracked implementation files. At review time, important untracked files included `backend/github.py`, `backend/integrations.py`, `scripts/prepare_github.py`, and `tests/test_github.py`. The base commit `b4f0551` predates them.

**Action:** review the complete branch diff, include the new implementation and tests in the feature commit, and push the feature branch when authorized. Keep `.env`, the SQLite database, virtual environments and raw diagnostic dumps excluded. This backlog does not authorize or perform a push.

**Acceptance:** a teammate can clone/check out the published feature branch, install dependencies, run all tests, and follow the documented preparation flow with their own credentials. A clean checkout contains the adapter, script and tests. Record the resulting commit SHA in this document or the PR so future line references have a stable baseline.

## ISS-013 — Filter available departments by the current actor

**Evidence:** `github_status` filters connections by an intersection with the actor's departments, but returns the entire connection's `department_ids`. Library intersects those IDs with the organization department list, not the actor's authorized list. A manager authorized for only one department can see another department as a creation option. `department_access` correctly rejects the unauthorized submission; this is not an authorization bypass.

**Files:** [backend/integrations.py](../backend/integrations.py), `github_status`; [static/app.js](../static/app.js), Library department select.

**Fix/acceptance:** return or render only departments the actor can publish to, with an explicit admin exception. Preserve the server check. Test a connection enabled for Support and Engineering with a manager authorized only for Support; Engineering must not be selectable. If there are no usable departments, explain the missing grant instead of rendering an empty required select.

## ISS-014 — Distinguish configured readiness from live connector health

**Evidence:** `github_status.connected` depends on active state, token presence and matching credential hash. It does not check token expiry/revocation or whether a specific selected repository is accessible. Connection setup tests a root directory and tool discovery; it does not exercise every possible file, issue query or repository.

**Proposed fix:** expose `configured`, `prepared`, `last_verified_at`, safe last failure category, and selected-repository check results separately. Label saved readiness honestly. Update health after an actual authentication failure without doing a live request on every UI poll. Add a short-lived repository probe if useful, with access-aware caching and rate limits.

**Acceptance:** a revoked token does not indefinitely display an unqualified healthy status after a failed read; a 404 on one repository does not mark all other repositories disconnected; no key appears in status; repeated page refreshes do not generate repeated external probes.

## ISS-015 — Apply replay protection to workspace bundle creation

**Evidence:** an isolated probe sent the same `POST /capabilities` bundle request twice as a manager with the same key. Different IDs were returned. [backend/app.py](../backend/app.py) enables idempotency for this endpoint only when `source == "github"`; [backend/registry/__init__.py](../backend/registry/__init__.py), `register`, always allocates a new ID. The frontend supplies a key for both sources, giving a misleading expectation of safe retry.

**Proposed fix:** apply the existing transactional replay mechanism consistently to capability creation, or explicitly distinguish non-idempotent operations in the client/API contract. Prefer safe creation retries. Preserve actor/resource permission checks and reject key reuse with a different payload.

**Acceptance:** lost-response retry yields one bundle and one logical creation audit event; a changed payload with the same key conflicts; two intentional creations with different keys remain allowed; unauthorized roles and permission changes are still rejected. Avoid deduplicating solely by a name, which may legitimately be reused.

## ISS-016 — Make custom workspace descriptions meaningful or label bundles honestly

**Evidence:** generic registry creation stores a name/description/tool list but no custom `skill`. Runtime gets built-in playbooks by executable tool names. The new GitHub path, in contrast, stores the creator's description in a playbook and adds it to runtime context. Therefore the same “What should it do?” field has different behavioral significance depending on source.

**Proposed fix:** choose an explicit contract: either a bundle is only a grouping and the UI says so, or custom purpose/instructions become a validated, versioned skill applied at runtime. Keep executable permissions separate from text instructions. A description must not manufacture a missing connector/action.

**Acceptance:** tests capture prompts for two differently described tools backed by the same action and verify the intended distinction; the Library explains grouping-only behavior where applicable; no description adds extra tools; conflicting skill purposes have deterministic handling.

## ISS-017 — Make bounded GitHub browsing explicit and navigable

**Evidence:** `github_list_issues` always requests `perPage=10`, with no cursor exposed. Output is plain text truncated at 30,000 characters. Discovery does not follow `nextCursor`. File reads do not expose an explicit branch/commit reference. The source URL returned by the wrapper is the repository root; upstream text may have more specific URLs, but the wrapper does not guarantee file/issue-level provenance.

**Proposed fix:** add optional bounded issue pagination, retain cursors/truncation metadata structurally, and provide source path/URL/revision fields. Consider pinning a task to a commit for consistent file evidence. Keep a total read/context budget, and do not offer unrestricted recursive crawling as a shortcut around ISS-001. Report unsupported binary/resource-only outputs clearly.

**Acceptance:** a repository with more than ten issues shows the sampling limit and can retrieve another bounded page if authorized; truncation is visible to both model and user; source citations identify the actual evidence; changing the default branch during a run does not silently mix revisions if revision pinning is implemented. Protocol pagination tests must not require production credentials.

## ISS-018 — Release SQLite write locks during setup model calls

**Evidence:** `Application.handle` starts a write transaction for POSTs and calls recruiter setup inside it. `recruiter.message` calls the external model before returning. SQLite uses `BEGIN IMMEDIATE` with a 60-second busy timeout. GitHub connector preparation already performs external I/O outside its write transaction, but recruiter setup does not.

**Impact:** one slow setup request serializes unrelated writes and can cause apparently frozen approvals/tool creation. This is a code-confirmed contention risk, not a load-test result.

**Proposed fix:** split setup into propose/read snapshot, external generation, and validated commit. Store draft revisions; after the network call, recheck actor authority, catalog/connection versions and expected revision before committing. Consider a setup job endpoint for slow providers.

**Acceptance:** deliberately block a fake setup model and perform an independent permitted mutation concurrently; it should complete promptly. Changing roles or draft revision during generation must prevent stale/unauthorized commit. A provider timeout should not leave partial hires or transactions open.

## ISS-019 — Bound activity-stream work and historical queries

**Evidence:** [backend/api/runtime.py](../backend/api/runtime.py), `activity_events`, can query a full activity snapshot every 0.75 seconds for 400 ticks. Snapshot construction scans organization/history tables through `all_rows`. Multiple authenticated tabs can open concurrent streams; there is no dedicated per-actor stream quota. Several ordinary list endpoints are unpaginated. Request-per-minute limiting does not bound the ongoing work of already-open streams.

**Proposed fix:** add bounded per-user/per-process stream accounting with cleanup on disconnect; paginate or window history; use targeted indexed queries; avoid reserializing unchanged full history. Retain periodic authorization/session checks. Preserve initial snapshots and reconnection behavior rather than using a lossy in-memory queue as the only state source.

**Acceptance:** opening excess streams is rejected predictably; disconnect frees the slot; token/department revocation closes access; a large seeded history does not make each tick scan every action; load tests report latency, database work and memory under multiple tabs. This ticket does not imply that a denial-of-service attack was observed.

## ISS-020 — Improve safe HTTP diagnostic correlation

**Evidence:** [backend/api/application.py](../backend/api/application.py), the generic exception handler logs only the exception class and returns a generic error. The transport supplies `X-Request-ID`, but the frontend discards it. Runtime unexpected exceptions do have run-ID tracebacks, so the gap is not “no runtime logging.”

**Proposed fix:** log sanitized request ID, operation, actor/organization identifiers where appropriate, and a server-side exception traceback; connect setup request IDs to eventual run IDs. Show a copyable support ID in the UI. Use a redacting logging boundary and avoid raw request bodies, Authorization headers, keys, prompts or repository contents in routine logs.

**Acceptance:** a deliberately injected unexpected HTTP exception can be traced from the UI ID to one server error record; secrets placed in test exceptions are redacted; expected validation/permission errors remain structured and do not flood traceback logs.

## ISS-021 — Decide repository authorization for private enterprise data

**Evidence/design:** a single server-managed token is shared across enabled departments. Backend department checks govern use of the connection; GitHub governs all repositories accessible to that token. There is no per-department repository allowlist or per-user GitHub identity. Thus enabling the connection for a department potentially permits its users to select any repository that the shared token can read, including public repositories and token-authorized private ones.

This matches the current demo's “user chooses a repository” design. It is insufficient if different departments must see different private repositories.

**Proposed decision:** retain explicit shared-demo access with non-sensitive data, or add per-connection/per-department repository policies and eventually GitHub App installations/per-user authorization. Keep repository selection dynamic within the authorized set. Do not revert to one hard-coded demo repository as the production authorization design.

**Acceptance before private enterprise use:** a Support user cannot read an Engineering-only private repository, even by submitting its URL directly; an explicitly permitted alternate repository works; policy changes are rechecked before dispatch and evidence reuse; the selected model provider is approved to receive the retrieved data.

## ISS-022 — Make skill/version behavior consistent

**Evidence:** built-in playbooks come from global `CAPS` through `playbooks_for(tool_names)`, while GitHub instructions come from bound database capability records. Built-in playbook edits can affect existing agents independently of an immutable skill-version upgrade; selected tool names can also pull in every matching built-in playbook rather than only a particular bound recipe. This behavior is partly documented as dynamic playbook updates.

**Proposed decision:** define whether instructions are pinned behavior or centrally updated policy. For pinned skills, store immutable versions/hashes and bind them explicitly. For shared platform policy, version and audit updates and label them separately. Avoid silently changing historical agent behavior while presenting all specifications as reproducible.

**Acceptance:** upgrading one skill changes only the intended agents after the documented approval/migration; historical traces identify the instruction versions actually used; creator descriptions and displayed playbooks agree with execution. Keep permission enforcement in code, not in versioned text.

## ISS-023 — Add realistic regression and browser coverage

**Evidence:** all 155 tests pass despite the reproduced budget starvation, post-failure thread block, missing-artifact success and bundle replay issue. Current GitHub workflow tests use a short mocked read → save → final sequence. Frontend tests run through Node VM with stubbed DOM elements; no actual browser layout, focus, scrolling or authenticated form submission is exercised.

**Plan:** add the regression tests specified in ISS-001/002/003/015, plus realistic GitHub file sizes, multi-call batches, long history, transient failures and wrong-path recovery. Add a browser smoke test using an isolated database, fake upstream GitHub transport and fake model, without production tokens. Keep a separate opt-in live connectivity smoke test with approved data and costs.

**Acceptance:** a manager can scroll to Add a tool, publish from a prepared connector, combine GitHub + Slides, choose a repository, run work, see actual evidence and a saved artifact, then recover from a failure. A builder sees the permission explanation; a manager cannot change connector credentials; repository/department restrictions remain enforced. Test mobile/keyboard form use and preserve text after errors.

## ISS-024 — Reconcile documentation with the current release

**Evidence:** `docs/IMPLEMENTATION.md` describes the bundled MCP architecture but does not explain the newly added GitHub adapter or the preparation-versus-publication split. The dated security review predates GitHub integration and manager tool creation, while README still links to it for controls and remaining gaps. Connection preparation has also moved from Library to a pre-demo script. The current implementation document's main approval paragraph already distinguishes agent/action policies correctly; retain that distinction rather than treating it as a new bug. Historical review results should remain historical rather than being silently relabeled current.

**Action:** add a dated integration addendum, update current implementation/role/approval matrices, and designate README + API docs as the operational contract. Explain the difference between a connector, a published skill/tool, an agent capability binding, a repository task input, and a saved artifact. Clearly retain “read-only GitHub” and “no arbitrary executable connector generation.”

**Acceptance:** a teammate follows the docs from a clean checkout without discovering hidden steps; manager/admin permissions match both UI and service tests; no document claims per-action pauses are universal; old test counts/review dates are labeled historical; no secrets or customer source content appear in examples.

## Suggested execution order

1. **Secure and share the baseline:** ISS-011 and ISS-012. Preserve the current working tree before rebasing or switching branches. Do not pop an old stash over these changes without reviewing it.
2. **Make the actual demo finish:** ISS-001, ISS-002, ISS-003, ISS-004 and ISS-008. Start with the deterministic saved-run shape: eight reads followed by a pending slideshow.
3. **Make errors recoverable:** ISS-005 as shared infrastructure, then ISS-006/007/009/010. Include ISS-015 while touching replay behavior.
4. **Improve clarity and evidence:** ISS-013/014/016/017/024 and the focused browser flow in ISS-023.
5. **Prepare for broader deployment:** ISS-018/019/020/021/022. Do not describe these as completed enterprise hardening until their acceptance criteria are tested.

Do not fix demo reliability by disabling role checks, removing the budget ceiling, silently switching models, granting a larger token scope, suppressing errors, or marking a run complete merely because it produced some text.

## Reproduction and verification guide

Use a temporary database for automated scenarios. Do not manually reset real failed runs to queued: their queue, action ledger, approvals, model call IDs and agent versions must remain consistent.

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
node tests/test_frontend_contracts.js
.venv/bin/python -m pip_audit -r requirements.txt --progress-spinner off
git diff --check
```

The audit used `/tmp/hackemhorns-verify-venv/bin/python` for backend checks; teammates should install `requirements-dev.txt` into their own environment. Test counts will increase as these tickets gain regression coverage. Loopback HTTP must be permitted because tests start the bundled MCP server.

Useful existing test files:

- [test_github.py](../tests/test_github.py): connector preparation, named tool publication, manager roles, repository choice, transport, and read → slides composition.
- [test_workspace.py](../tests/test_workspace.py): isolated application fixtures, artifact tools, task conversations and schemas.
- [test_hardening.py](../tests/test_hardening.py): work-queue quality, scope, provider retry, concurrency and idempotency cases.
- [test_runtime_revalidation.py](../tests/test_runtime_revalidation.py): authority/spec/policy changes during model execution.
- [test_auth.py](../tests/test_auth.py): password sessions, CSRF, revocation and production checks.
- [test_fastapi.py](../tests/test_fastapi.py): strict API contracts and transport behavior.
- [test_frontend_contracts.js](../tests/test_frontend_contracts.js): current lightweight frontend contracts; supplement with real browser checks.

Read-only SQL for finding additional saved failures (the database stores JSON documents):

```sql
SELECT id,
       json_extract(body, '$.status') AS status,
       json_extract(body, '$.error_code') AS error_code,
       json_extract(body, '$.max_steps') AS max_steps,
       json_extract(body, '$.model_turns') AS model_turns
FROM runs
WHERE json_extract(body, '$.status') = 'failed';

SELECT json_extract(body, '$.tool_id') AS tool,
       json_extract(body, '$.status') AS status,
       COUNT(*) AS count
FROM actions
WHERE json_extract(body, '$.run_id') = '43882f20-41e9-4900-906a-4e7fa447bae3'
GROUP BY tool, status;
```

Do not attach complete `runs.body`, model histories, tool results or `.env` to a public issue. Share only the identifiers, sanitized error category, bounded counts and minimal synthetic reproduction needed for the assigned fix.

## Demo release checklist

- [ ] Credential rotation and feature-branch handoff completed.
- [ ] GitHub connector prepared before the demo; the desired new tool is created live at the bottom of Library.
- [ ] Manager can create it; builder cannot publish; connector setup remains admin-controlled.
- [ ] GitHub + Slides task saves an actual deck within its enforced budget.
- [ ] Near-budget, missing-file and transient-error cases have understandable outcomes.
- [ ] Failed/cancelled tasks can be retried through the displayed recovery flow.
- [ ] A missing output cannot be reported as a successful saved artifact.
- [ ] Repository selection remains dynamic and within connection/data policy.
- [ ] Long results and sampled issues are labeled; no whole-repository audit claim is made.
- [ ] Full backend/frontend checks and an isolated browser smoke test pass on the published branch.

When closing a ticket, record its commit/PR, test names, verification result, migration implications and any remaining scope limitation here or in the tracking issue.
