# Android reference implementation review

Source visual truth: `output/android-xiaomi-17-pro-max/{overview,nodes,users,subscriptions,settings}.png`.
Implementation: `output/ui-audit/412.0-page-{0..4}.png`; narrow variants `320.0-page-{0..4}.png`.
Comparison: `output/reference-comparison/index.html`, with a paired image for each page (source left, implementation right).

## Scope and normalization

Reference pixels: 1200 × 2608, resized for comparison to 412 × 895. Actual Flutter captures: 412 × 895 logical pixels, DPR 1. Secondary viewport: 320 × 740. Native status/navigation system bars are excluded from widget-test captures. These are native widget renders with explicit fixtures, not device screenshots or screenshots of a web substitute.

State: dark theme; overview with telemetry; first node expanded; ordinary users with first user and More expanded; first subscription expanded and its More popup open; settings at top. Counts, dates, names and sampled time series are fixture data and are not required to equal the illustrative mock. Production continues to read the API. Missing telemetry is shown as unavailable, not replaced with illustrative numbers.

## Comparison history and fixes

- P1: old overview service banner, large independent stats, shared budget list and service controls replaced the source structure. Replaced with a compact two-column statistics block, aggregate graph and separate node cards. Service controls moved into Settings.
- P1: old user and node rows opened only modal details. Replaced with in-place expandable cards, retaining full operational details behind explicit controls. Node enrollment moved to Node Management.
- P1: old Settings was an application identity block followed by an ungrouped grid. Reordered into service/system, network, backup/restore and panel update sections. App update, account management and appearance remain below these sections.
- P2: old green selection pills, large rounded cards and inconsistent controls. Replaced with navy bordered surfaces, cyan highlights, purple selection/action accents, unified bottom navigation and compact controls.
- P2: 320px/2x-text service and node action rows overflowed. Added wrapping and single-column fallbacks; repeated the responsive tests after fixing them.
- P2: inline user mutations could dismiss the main route because prior handlers assumed a modal. Restricted dismissals to popup routes and added a test proving inline disable updates the card without popping the main page.
- P2: subscription popup covered its trigger. Anchored the popup below the trigger and used the shared bordered surface.

## Fidelity surfaces

- Typography: common title, body, metric and control hierarchy; native Material/system font fallback. Source is a raster mock and does not supply an original font file. Exact glyph/antialiasing identity is not asserted.
- Spacing/layout: five source page structures implemented. Page margins, border radii, control density and navigation are shared. Cards grow for long live content, accessibility text scaling and additional required actions.
- Color: dark navy canvas/cards, blue borders, cyan primary metrics and purple secondary metrics/actions. User-selected accent remains functional.
- Assets: native Material outline icons, existing app identity asset, real painted charts. No screenshot is used as an interactive screen or data surface. The mock's subtle decorative raster texture is not reproduced.
- Content: backend values and error/empty/stale states remain live. Ordinary/premium switching, full details, App update and safeguards are retained even where the mock omits them.

Full-view evidence: the five paired images linked above were inspected. Focused evidence: expanded user actions, subscription More popup, resource controls and navigation are readable in the normalized paired captures and were also inspected at native capture size.

## Validation

157 Flutter tests passed, including stale-response ordering, duplicate submissions, cancellation/disposal, user types, subscription changes, errors and the new inline-route regression. Two opt-in capture tests passed independently. 320px with 1x/2x text and both themes passed the responsive suite. Static analysis passed. APK debug arm64 build succeeded.

## Expected differences and remaining verification

The ordinary/premium selector, explicit full-details entry, App update section, native glyphs/icons and live-data-dependent height are intentional product/runtime differences. Numerical and graph shape differences are fixture differences. Fine raster texture and icon contours remain P3 polish; this review does not certify pixel identity. No connected Xiaomi device was available; physical-device system bars, font substitution and installation remain unverified.

final result: passed
