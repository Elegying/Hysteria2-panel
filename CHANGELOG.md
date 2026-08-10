# Changelog

## [0.3.2] - 2026-08-10

### Fixed

- Remove the remaining panel-unit sandbox directives that implicitly block setuid, allowing the exact sudoers-approved service controls to work. The panel keeps read-only system, private temporary directory, home/control-group protection and resource limits; the Hysteria server keeps the full sandbox.

## [0.3.1] - 2026-08-10

### Fixed

- Allow the panel's exact sudoers-approved Hysteria service controls to execute by removing the incompatible `PrivateDevices=true` sandbox from the panel unit. The Hysteria server unit keeps the sandbox.

## [0.3.0] - 2026-08-10

### Added

- Per-user concurrent connection and total traffic limits with defaults of 3 connections and 250 GiB.
- Durable upload/download accounting, quota progress, per-user reset and reset-all controls.
- Recoverable server-key-derived sharing credentials and one-click URI copying.
- Dark operations dashboard with system resources, top-five traffic users, version checks and Hysteria service controls.

### Changed

- Hysteria authentication now rejects users at their connection or traffic limit while preserving the official HTTP auth response contract.
- The installer grants the panel an exact sudoers allowlist for only start, stop and restart of its namespaced Hysteria service.

## [0.2.1] - 2026-08-10

### Fixed

- Prevent HTTP login loops when a browser still has the legacy HTTPS-only session cookie.
- Avoid request-logging exceptions when HTTPS traffic is mistakenly sent to the HTTP panel port.

## [0.2.0] - 2026-08-10

### Added

- Prompt for a shared node label and use it as every generated URI fragment.
- Optional HTTP panel mode with scheme-aware cookies, HSTS and health checks.
- Dashboard cards for service status, current users, inactive users, online devices, total upload and total download.
- Persistent quic-go UDP send/receive buffer tuning and an increased Hysteria file-descriptor limit.

### Changed

- Re-running the installer now applies the supplied administrator password instead of silently ignoring it when an administrator already exists.

## [0.1.2] - 2026-08-10

### Fixed

- Accept Hysteria's successful empty response body from `POST /kick` instead of misreporting a JSON decoding failure.

## [0.1.1] - 2026-08-10

### Fixed

- Wait up to 30 seconds for the HTTPS panel and local authentication endpoint to become ready after a systemd restart.

## [0.1.0] - 2026-08-10

### Added

- Checksum-pinned one-click installation of Hysteria 2 `v2.12.1` for Linux amd64 and arm64.
- Dynamic multi-user authentication through Hysteria's local HTTP callback.
- HTTPS administration panel with CSRF protection, rate-limited login and hardened cookies.
- One-time user credentials, certificate-pinned connection URIs, traffic statistics and connection kicking.
- Isolated system identities, bounded request concurrency, hardened systemd services, upgrade backups and health checks.
