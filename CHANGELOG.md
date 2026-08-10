# Changelog

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
