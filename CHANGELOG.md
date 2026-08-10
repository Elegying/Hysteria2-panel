# Changelog

## [0.9.1] - 2026-08-11

### Changed

- Display BBR status and the current version as two independent cards matching the service summary layout.
- Move user search into the management header and remove its visible label while retaining an accessible name.

## [0.9.0] - 2026-08-11

### Added

- Search all users instantly by name from the dashboard.

### Changed

- Show the complete user list without pagination.
- Move user creation into a responsive dialog opened beside the global traffic-reset action.

## [0.8.0] - 2026-08-11

### Added

- Display the explicit Hysteria QUIC BBR profile together with the live Linux TCP congestion-control and queue-discipline state beside the current version.

### Changed

- List newly created users first by default while preserving total-traffic sorting.
- Pin Hysteria's non-Brutal congestion controller to BBR with the standard profile in one-click deployments.

## [0.7.0] - 2026-08-10

### Added

- Sort the user list by total traffic in ascending or descending order from the table header.
- Show newly created node information in an in-page dialog with a copy button.

### Changed

- Copy a user's Hysteria 2 URI directly from the Share action without leaving the dashboard.
- Keep each mobile user in one compact row with all five actions visible and no horizontal scrolling.
- Put top-user traffic beside the username and stretch the three desktop operations cards to equal height.
- Remove the repeated concurrent-device-limit note below each username.

## [0.6.1] - 2026-08-10

### Fixed

- Separate the mobile login action from the password field so the button never overlaps the input.
- Restore consistent spacing between service summary and version cards.

### Changed

- Place service controls, system resources and top traffic users in one compact desktop row.
- Reduce the footprint of service statistics, port, version, update and resource cards while keeping two-column summaries on phones.

## [0.6.0] - 2026-08-10

### Added

- Add a native, keyboard-accessible data migration dialog opened from the dashboard header.

### Changed

- Tighten desktop dashboard spacing and reorganize mobile navigation, overview metrics and service controls.
- Convert the wide user table into labeled touch-friendly user cards on phone-sized screens while preserving the desktop table.

## [0.5.1] - 2026-08-10

### Fixed

- Restart the TCP 19999 compatibility probe after every backup restore, including restore validation failures, so TCP-only latency checks remain available with the Hysteria service.

## [0.5.0] - 2026-08-10

### Added

- Add one-click ZIP download and upload restore for all proxy users, durable traffic, the HMAC signing identity, TLS certificate/private key, certificate pin and migration metadata.
- Add strict archive, SQLite, user-token, certificate/key, fingerprint and endpoint validation plus an isolated root oneshot restore service with automatic pre-restore backup and rollback.

### Changed

- Preserve the destination panel administrator and deployment-only settings during restore while invalidating all prior panel sessions. Old client nodes remain usable only when the public host and UDP port are unchanged; certificate renewal or rotation requires re-sharing the new pin.

## [0.4.0] - 2026-08-10

### Added

- Add a hardened TCP connectivity probe on the same numeric port as Hysteria UDP, allowing TCP-only client tests to complete without exposing panel or authentication data. The probe follows the Hysteria service lifecycle and does not replace a protocol-level health check.

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
