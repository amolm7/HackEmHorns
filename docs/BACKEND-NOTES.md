# Backend notes from the UI redesign — implementation status

Reviewed and implemented against the existing authorization and durable runtime. The visual design remains unchanged.

| # | Resolution |
| --- | --- |
| 1 · Three-call creation | `POST /agents/quick-create` validates, creates a proposal, and confirms when authorized in one database transaction. It requires an idempotency key. Failures roll back drafts and validations. The UI now makes one request. |
| 2 · Builder activation | Manager confirmation is retained. The endpoint returns `awaiting_confirmation` with a durable proposal. The builder sees who must confirm; Approvals includes pending hires in its badge for both creator and assigned manager. No builder self-activation or broader access was introduced. |
| 3 · Naming | Defaults describe the selected capabilities and receive an organization-unique numeric suffix. Names are checked against agents and pending drafts. Explicit names are preserved. Existing versioned `PATCH /agents/{id}` rename support is exposed in the agent menu. It retains the existing reset/invalidation semantics, with a UI notice. |
| 4 · Demo reply | Completed demo runs persist `result.answer`, generated from executed tool steps. It labels demo mode and local-only outputs. The browser no longer invents successful-work narration. Older records use their saved summary. |
| 5 · Approval questions | New actions persist a readable `summary`. The summary is included in the frozen approval hash and displayed by the UI alongside exact arguments. Older saved actions remain compatible. |
| 6 · Polling | `GET /agents/{id}/runs` and `/activity` scope reads to one agent. `/events` streams durable snapshots of run status, steps, approvals, and conversations. The open chat uses one authenticated fetch stream with reconnects and heartbeats, and defers rendering while typing. Other workspace screens retain slower polling for cross-agent state and pending hires. |
| 7 · Add tools | `POST /agents/{id}/capabilities` checks manager authority, expected spec version, and bindings; adds tools and records a version atomically. Adding authority always resets to Intern/asks-first and invalidates previous runs. Duplicate already-bound additions are a no-op. The UI makes one request. |
| 8 · Conversations | `POST`/`GET /agents/{id}/conversations` persist actor-owned conversations separately from recruiter conversations. Runs carry `conversation_id` and compatible `thread_id`. New conversations survive reloads. Live messages continue only the same owner, agent, model, and latest completed turn. Existing `follow_up_of` clients and saved threads remain supported. |
| 9 · Cleanup | `DELETE /agents/{id}` soft-archives for the manager/admin. It cancels unfinished work and pending approvals, preserves history, and refuses to archive an in-flight tool call. Archives are omitted from normal lists; `GET /agents?include_archived=true` retains administrative/history visibility under existing access rules. Archived agents cannot run or be reactivated through editing. |

## Limits

The stream delivers state updates, not model-token streaming. It samples SQLite state every 750 ms, sends only changed snapshots, rechecks access each cycle, and holds no transaction while waiting. Connections reconnect after five minutes. This is appropriate for the single-process prototype; distributed event delivery and provider streaming remain future work. A bounded conversation still uses the existing 60 KB context limit. No production authentication, external notification service, or global connector discovery was added.

The two self-hosted fonts remain unchanged.
