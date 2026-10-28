# Combined Claude integration — 28 October 2026

This combines revised B1 PR44, B2 rev2 contract/schema/tooling PR45, and the application-shell/onboarding PR46. The owner explicitly selected Claude's latest main theme. Historical Meta contributions remain accurately scoped; no new Meta call is claimed.

Integration conflict: both branches extended src/runtime/api_v2.py route constants. The merged constants retain onboarding and recovery acknowledgement. No routes were dropped.

Failed-first integration fixes:
- APK download now checks expiry in its request handler, independent of timer scheduling. Explicit stop cancels its daemon shutdown timer.
- Invocation ledger never expires an in-flight entry; completed-result retention starts at completion. A concurrency regression reproduced duplicate dispatch before the fix.

Validation: combined source passed466 tests before added regressions; 468 passed after APK regressions, and15 focused contract tests passed after the in-flight fix. Final complete count and CI are recorded in the PR. Five controlled browser modules passed at390/768/1440/3440: offline, Fabric, guided, exact-action consent and trusted Forge selection. No real hardware/model calls were made. Compileall, theme check and diff check passed.

Remaining: B2 runtime provider/routing/policy/invocation endpoints, live Skill Graph consumer, new fair protocol evaluation, real failover and Watch-to-TV control, coordinated live-app reload and final participant submission review. Contract/schema helpers and a planned graph are not those implementations. Multi-PC assessment is scheduled for29 October09:00 Paris; no previously blocked port workaround. No videos until a NEW explicit request.
