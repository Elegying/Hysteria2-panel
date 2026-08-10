# Implementation Plan: Operations dashboard and user limits

## Overview

Extend the existing single-file Python panel without adding a web framework. Preserve the current database and authentication model while adding durable traffic accounting, concurrent-connection limits, recoverable encrypted share credentials, system metrics, service controls, update checks, and the supplied dark operations-dashboard layout.

## Architecture Decisions

- Treat the requested device limit as a concurrent Hysteria connection limit because the official `/online` API exposes connections per auth ID, not physical device identity.
- Persist upload/download deltas in SQLite by periodically collecting Hysteria `/traffic?clear=true`; quotas and resets use this durable ledger.
- Derive recoverable proxy tokens from a random per-user seed and the existing server HMAC key. The database never stores the token itself; legacy users remain valid and become shareable after their next explicit rotation.
- Restrict service controls to an exact `systemctl` allowlist installed through sudoers; no user input reaches a shell command.
- Keep the panel dependency-light and server-rendered; use a CSP nonce only for clipboard and confirmation interactions.

## Task List

### Phase 1: Limits and durable traffic

- [x] Add backward-compatible SQLite columns and recoverable server-key-derived credential support.
- [x] Add traffic collection, quota enforcement, reset operations, and connection-limit enforcement.

### Checkpoint: Policy core

- [x] Database migration and auth-policy tests pass.
- [x] Existing authentication remains compatible.

### Phase 2: Operations services

- [x] Add system-resource sampling, top-five traffic ranking, version checks, and service status/control adapters.
- [x] Extend the installer with the exact service-control permission and release dependency checks.

### Checkpoint: Operations core

- [x] All privileged actions require authenticated CSRF-protected POST requests.
- [x] No arbitrary command or URL input is accepted by the operations adapters.

### Phase 3: Dashboard and sharing UI

- [x] Rebuild the dashboard to match the supplied dark blue reference at desktop and mobile widths.
- [x] Add user limits to creation, quota progress, share/reset actions, global reset, service controls, resources, version state, and high-traffic users.
- [x] Add nonce-protected one-click clipboard copying and clear confirmation states.

### Checkpoint: Complete

- [x] Full unit/integration suite, compile, shell syntax, ShellCheck, and browser console checks pass.
- [x] Reference-to-implementation visual QA passes.
- [ ] CI, release, backup deployment, production login, service control, limits, sharing, and data preservation are verified.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Physical devices cannot be identified by Hysteria | Medium | Enforce concurrent authenticated connections and label the behavior accurately. |
| Traffic could be lost during a hard crash | Medium | Collect/clear frequently and sync before resets, auth decisions, and managed restarts. |
| Service controls elevate privileges | High | Exact service/action allowlist, CSRF, audit logging, fixed subprocess argv, no shell. |
| Existing token cannot be recovered from its HMAC fingerprint | Medium | Preserve it unchanged; require one explicit rotation before the share button can reproduce a URI. |
| HTTP panel exposes credentials in transit | High | Preserve the user's requested mode but keep the warning and recommend restricted access. |

## Open Questions

- None blocking. Default limits are 3 concurrent connections and 250 GiB total traffic.
