# Backend operations

This release is intended for a small, single-company pilot. It has not undergone an independent security review, load test or disaster-recovery exercise on your deployment infrastructure. Deploy behind HTTPS; do not expose development impersonation.

## Password accounts

Provision users from a trusted terminal on the server. Passwords are prompted without echo and never passed in arguments or written to `.env`:

```sh
.venv/bin/python scripts/create_user.py --username pavan --actor pavan
.venv/bin/python scripts/create_user.py --username amol --actor amol
.venv/bin/python scripts/create_user.py --username tarun --actor tarun
.venv/bin/python scripts/create_user.py --username shaun --actor shaun
```

`--actor` links a login to an existing server-owned role record. It does not grant roles chosen by a browser. The seeded roles are Pavan (manager/builder), Amol (admin/manager), Tarun (manager), and Shaun (builder). Provision only people who should have that actor's permissions.

Set the literal `AUTH_MODE=password` in `.env` and restart. Your actual password does not belong in `.env`. Accounts use unique salts and scrypt with N=32768/r=8/p=1. Sessions expire after eight hours, are revocable, and store only a hash of the opaque session credential. Password reset invalidates existing sessions. Mutations require a CSRF header returned by `/api/auth/session`; the browser handles it. Production cookies use the `__Host-` prefix, Secure, HttpOnly and SameSite=Strict. Local HTTP cookies use a separate name.

Operator recovery and access revocation:

```sh
.venv/bin/python scripts/create_user.py --username pavan --reset-password
.venv/bin/python scripts/create_user.py --username shaun --disable
.venv/bin/python scripts/create_user.py --username shaun --enable
```

Disable revokes sessions and removes the actor's permission to advance queued jobs. An action already dispatched cannot be undone. Re-enabling does not restore old sessions. Login is limited to 10 attempts per account and 30 per client IP in five minutes; two password checks may execute concurrently. These are process-local limits; put a rate limiter at the ingress before expanding beyond a small pilot. Self-service password recovery and MFA are not implemented.

## Execution guarantees

- Workflow jobs advertise and execute only the tools required for that workflow, within the agent's existing capability and connection permissions.
- Deliverable checks verify presence, slide count/content, required document headings/length, original CSV identity, and ticket/draft identity. They do not verify factual accuracy or compliance with arbitrary prose rules. Managers review those.
- A live job gets at most one automatic deliverable repair attempt. Failed reports are preserved in its trace and visible in Team jobs.
- Revision attempts receive prior outputs and manager feedback. The original brief and data remain authoritative. Attempts retain separate run IDs and prior outputs are not overwritten.
- Queue creation, sample loading, assignment and outcome review require `Idempotency-Key`. Retry the identical payload with the same key; changing the payload returns a conflict. Permission changes also invalidate replay. Legacy keys created before this release cannot be replayed.
- Temporary provider timeouts, 408, 429 and selected 5xx failures receive bounded scheduled retries. Retry state survives restarts; cancellation remains available while waiting. Permanent authorization failures are not retried. Repeating a model request may incur provider charges even if the earlier response was lost.
- Only bundled local write tools have durable execution deduplication. Do not extend their crash-recovery guarantees to external APIs without implementing external idempotency.
- Web fetches block private addresses, revalidate redirects and connect to the vetted IP while preserving TLS hostname verification. Proxy environment variables cannot bypass that boundary.

## Worker and storage

`WORKER_CONCURRENCY` defaults to 2 (range 1–8). `MODEL_MAX_RETRIES` defaults to 3 (range 0–5). `MAX_ACTIVE_RUNS` defaults to 50 per organization and `MAX_ACTIVE_RUNS_PER_USER` to 10, including jobs waiting for approval. New submissions receive 429 when full. `MAX_RUN_OUTPUT_TOKENS` defaults to 20000 and prevents further model calls after the reported output-token budget is reached (the last call may cross that threshold). These bounds do not replace provider-side billing limits. One scheduler owns each SQLite database using an OS lock. Run **one Uvicorn process**, on Linux or macOS, per database. Worker threads can execute independent jobs concurrently; a job cannot be scheduled twice by that scheduler. Stop waits for in-flight calls before closing MCP services and releasing the lock.

SQLite uses WAL, transactions, additive indexes and schema version 1. Database and backup files use owner-only permissions. JSON documents remain compatible with existing data. For horizontal scaling, migrate to a shared database and durable distributed job queue; do not run several workers against a shared SQLite file or network filesystem.

## Health and diagnostics

- `/api/health`: process liveness.
- `/api/ready`: database connectivity and scheduler readiness; returns 503 if unavailable.
- Responses carry `X-Request-ID`; platform errors include it in their details.
- Production emits JSON request logs containing request ID, method, path, status and duration. Request bodies, authorization cookies and passwords are not logged by this logger. Configure retention and protect infrastructure logs separately.
- `REQUESTS_PER_MINUTE` defaults to 1800 per client IP, per process. Behind a proxy, clients may share an IP; tune and add an ingress limiter before scaling. Forwarded IP headers are deliberately not trusted.

## Backup and recovery

Create an online, consistent backup, including committed WAL data:

```sh
.venv/bin/python scripts/backup.py
.venv/bin/python scripts/backup.py --verify data/backups/YOUR_BACKUP.sqlite3
```

Backups refuse to overwrite existing paths and run SQLite integrity checks. They contain company data and credential hashes: keep them private, encrypt off-host copies, and apply a retention policy. The test suite restores a backup into an isolated application and verifies its contents.

For an actual restore: stop the application; preserve the current database and its WAL/SHM files together in a separate recovery directory; copy a verified backup to a **new** database path; set `DATABASE_PATH` to that new path; start and verify it. Never replace a live SQLite database or mix a restored database with stale WAL files. A restored backup can contain sessions valid at backup time; before reopening access, revoke its sessions (`UPDATE auth_sessions SET body=json_set(body,'$.revoked',json('true'));`) from a trusted SQLite connection.

## Deployment configuration

```env
APP_ENV=production
AUTH_MODE=password
APP_ORIGIN=https://agents.example.com
DATABASE_PATH=/app/data/workforce.sqlite3
WORKER_CONCURRENCY=2
MODEL_MAX_RETRIES=3
```

Production startup rejects development authentication, an HTTP/missing origin, or an absence of active provisioned accounts. Keep provider keys in your deployment secret store or ignored environment file. Use a TLS reverse proxy with the canonical Host header; the origin and Host must match `APP_ORIGIN`.

The Dockerfile runs as UID 10001, excludes local secrets/data from its build context, and has a readiness health check. Build and mount a persistent volume, provision accounts using `scripts/create_user.py` against that volume, then start the production container behind your TLS proxy. Bind the container port to loopback until the proxy is configured. The Docker image has not been built in this workstation session; validate it and pin a tested base-image digest in your deployment pipeline.

`.github/workflows/tests.yml` runs the backend tests and JavaScript syntax checks on pushes and PRs. The pipeline itself must be observed after pushing; local checks do not prove a GitHub Actions run passed.

## Before handling real company data

Complete a deployment-specific security review, TLS and backup/restore drill, account/role review, provider data-processing review and realistic concurrency/load test. Add MFA or a managed identity service for higher-risk use. Encryption-at-rest and off-host backups depend on your infrastructure. No external messages, purchases or publishing are enabled by this local tool catalog.
