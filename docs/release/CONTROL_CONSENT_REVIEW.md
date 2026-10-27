# Exact-action consent review — 27 October 2026

Base `2dd79af`; code ownership: main presentation only. No runtime/adapter/Companion changes.

A PC job's checkbox approves one exact command. Previously changing its shell left consent armed. The panel now invalidates consent on command or shell changes, snapshots both fields before dispatch, consumes consent immediately and locks the form until completion. It offers no automatic retry.

The robot panel previously reused a single-change checkbox across commands and selected Undo's setting from the mutable dropdown. Each change/command now consumes consent before dispatch. A verified change binds Undo to its original setting; editing the dropdown cannot redirect it. In-flight controls are disabled; request failures are displayed and controls released. The existing backend remains responsible for authorization, exact restoration and device state; this UI fix does not establish new physical-device proof.

Failed-first evidence: controlled browser assertions failed on shell-change consent, then on robot consent reuse before the corresponding fixes. The controlled test invokes the actual panel functions extracted from app.js, with fake postJson and no server/device/model access. It covers all four widths (390/768/1440/3440), exact job params, in-flight locks, original-setting Undo and refusal of a second robot command without new consent. The test is added to the existing CI browser job.

Validation: 441 unit/integration tests passed (34.775s); compileall and theme source check passed; control_consent_smoke, fabric_smoke and guided_smoke passed at four widths. Git diff check passed. This is targeted automated evidence, not a full accessibility or security certification. No hosted request, hardware operation, desktop keyboard/mouse automation or video.
