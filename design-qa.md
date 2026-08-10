# Design QA

## Reference comparison

- Reference dashboard: `codex-clipboard-09e83780-9db7-42d1-8579-00a945b9e300.png` (2714 x 1382).
- Reference user toolbar: `codex-clipboard-d60dc657-de65-41b2-82fd-d15004960663.png` (2658 x 324).
- Implementation dashboard capture: `docs/screenshots/dashboard-1380x702.png` at a 1380 x 702 CSS viewport.
- Implementation user-management capture: `docs/screenshots/user-table-1380x702.png` at the same viewport.
- Mobile viewport capture: `docs/screenshots/dashboard-mobile-375x812.png` at 375 x 812.

The reference and implementation captures were inspected together at matched display widths. The implementation preserves the reference's dark navy operations-dashboard hierarchy, compact status pills, four summary cards, two-column operations area, bordered resource tiles, high-contrast service controls, and dense user-management surface. Product-specific Hysteria controls and traffic limits replace the SSR-only fields from the reference.

## Functional and responsive checks

- Login succeeds and reaches the dashboard.
- Update checking renders a newer-version link without a script error.
- Creating a user with 4 devices and 123 GiB shows the exact limits and a 0.0% progress bar.
- Share opens a Hysteria 2 URI and the HTTP-compatible copy fallback changes the button to `已复制`.
- Restarting Hysteria returns to a running state.
- The 375 x 812 viewport has no horizontal overflow; the header, metrics, and controls reflow into mobile columns.
- A console/network scan after reload reported no JavaScript exceptions, browser log errors, or failed page loads.

## Result

passed
