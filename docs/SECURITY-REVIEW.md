# Security and hackathon track review

Reviewed October 24, 2026. This is a source and automated regression review of the current prototype, not an independent penetration test or a production certification.

## Fixes

| Finding | Change | Verification |
| --- | --- | --- |
| Cached POST responses checked the caller's permissions but ignored later changes to the resource's department, manager, or ownership. | Cache entries now fingerprint the authority fields of referenced resources and their agents. Changed authority returns `409 replay_access_changed` without repeating the mutation. | Replay after a department transfer or manager reassignment is rejected; an unchanged replay returns the original result. |
| An already-confirmed proposal could return its agent to the original manager using a fresh request key after reassignment. | Confirmation rechecks the current agent's management permissions. | Fresh-key confirmation by the former manager returns 403. |
| Approval inbox reads retained access after a manager lost department access. | Inbox reads check current agent visibility. Management and proposal access also check current department access. The unused approval-detail endpoint remains removed, as in main. | Revoked access removes inbox/proposal entries and denies approval decisions. |
| Calendar TEXT fields escaped LF but allowed CR to introduce additional properties. Attendee values had insufficient validation. | Normalize line endings, remove invalid controls, escape calendar text, and restrict calendar attendee URIs to email-shaped values. | Malicious title/location/attendee inputs cannot introduce extra event or attachment properties. |
| Explicit meeting timezone offsets were dropped from downloadable invites; date-only input silently scheduled midnight. | Serialize timezone-aware calendar dates in UTC and reject dates without a time. | Offset conversion, end time, date-only rejection, and existing floating-time behavior are covered. |
| Provider error bodies could echo the configured API key into persisted/displayed errors. | Both model adapters redact their credential before truncating the error excerpt, and remove bearer token values. | Mocked Meta and Gemini failures cannot expose the configured key or a bearer token. |
| Malformed URL ports could escape as generic server exceptions. | Return a controlled validation error before DNS/network access. | Invalid numeric/text ports and malformed IPv6 syntax are covered. |
| The HTTP schema allowed ten tools in a custom capability, while the service accepted only three. | Align the service with the bounded ten-tool bundled catalog contract. | Registration with the full bundled catalog succeeds. |

Older cached mutations without the new authority fingerprint fail closed with 409. Refresh the resource before deciding what to do next; do not automatically resubmit with a new key, because the original mutation may already have completed. Execution/status updates alone do not change the authority fingerprint.

## Checks and existing protections

- Backend suite: 141 tests, including 11 new regression tests. Tests use isolated temporary databases and mocked model responses; local MCP calls use actual loopback HTTP.
- Frontend syntax and contract checks: `node --check static/app.js` and `node tests/test_frontend_contracts.js`.
- `git diff --check` for patch whitespace.
- `pip-audit -r requirements.txt`: no known vulnerabilities reported for the resolved runtime dependencies on the review date. This is advisory coverage, not proof that dependencies are vulnerability-free.
- Tracked-file credential-pattern scan: no matches for the checked Muse/Google/private-key patterns. This is not a complete secret-history audit. The local `.env` is ignored and has mode 0600.
- Reviewed password hashing, session revocation, CSRF, host/origin policy, body limits, CSP, static-file allowlisting, parameterized SQL, scoped tool dispatch, action snapshots, connection validation, queue recovery, network redirects, and DNS pinning. Existing tests cover these boundaries and were retained.

Live provider credentials and live model availability were not exercised in this review. Automated provider checks are mocked. Browser visual/accessibility testing and external penetration testing were not performed.

## Fit to the original prompt

**Yes: the prototype addresses reusable enterprise agent setup.** The core value is the approved configuration that can be reused, rather than a collection of unrelated chatbots.

| Track requirement | Current implementation |
| --- | --- |
| Reuse tool setup | Versioned capabilities, schemas, authorized connection binding, bounded validation evidence, internal publishing and installation. |
| Reuse model configuration | Server-side Meta/Gemini adapters and a fixed model profile per agent; deterministic demo mode is labeled separately. |
| Reuse instructions | Job-specific agent instructions plus the playbooks for approved tools. These guide the model; they do not fine-tune it or guarantee expertise. |
| Add monitoring once | Shared durable runs, tool steps, approvals, audit events, outcomes, and usage/reuse metrics. |
| Let users focus on the goal | Describe a job or choose capabilities, review the proposed agent, run work, and inspect the deliverables. Templates avoid rebuilding configuration. |
| Enterprise controls | Password sessions, role/department checks, manager confirmation, configurable action review, versioned specs, bounded runtime, and portable templates that omit credentials and trust. |

For the judging demo, show one complete reusable workflow: create a specialist, run a job, inspect its tool evidence/result, publish the template, then install it with local connection validation. Keep the leaderboard secondary to that story.

## Material limits before production

- This is one seeded company and a single application process/SQLite database, with a bundled local MCP integration. It does not yet connect arbitrary enterprise services or provide fully administered multi-tenant onboarding.
- Enterprise SSO, managed credential rotation/vaults, external connector OAuth, and provider-specific write reconciliation remain future work. Local draft retries are deduplicated; this does not guarantee exactly-once writes to future third-party systems.
- Models can produce inaccurate content or follow hostile instructions found in retrieved text. Backend tool scopes constrain available actions; they do not establish factual correctness or prevent all disclosure to the selected model provider. Use approved data and human outcome review.
- Agent-level approval is the default: the manager approves the scoped agent once. Per-action review is optional, and `require_all_approvals` can impose stricter review. Promotion does not add tools or credentials. Documentation must not promise that every default-mode tool call pauses for approval.
- Queue/concurrency/step/output limits exist, but there is no hard monetary budget, distributed rate limit, or dedicated stream-connection quota. Public hosting needs deployment-level connection limits, TLS, backups, monitoring, retention rules, and load testing. Setup model calls still hold a database write transaction and can serialize other mutations.
- Capability validation and quality checks are bounded fixture/structural checks, not a benchmark proving domain skill or a security certification. Leaderboard usage is distinct from demonstrated quality.
- API keys previously shared in the conversation should be rotated at the providers. Keeping `.env` ignored protects Git; it does not revoke exposed credentials. No credential rotation was attempted by this review.

The project is a credible hackathon prototype of an enterprise agent platform. Present the controls and working reuse honestly, and describe the remaining production integrations as roadmap work.
