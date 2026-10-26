# OpenBridge — Meta visual design proposal

English translation and condensed implementation notes from the actual Meta Muse Spark 1.3 response. The original response is retained privately for provenance; docs/meta-design-receipt.json records its model, request ID, usage and original prompt hash. This translation is editorial work, not a second Meta generation.

## Direction

A workbench instrument rather than a generic dashboard. Three principles: distinguish simulation from real devices, prioritize offline/unauthorized/empty states, and keep read-only limits explicit. Source selection and a persistent mode banner should use factual verbs such as List and Inspect rather than implying repairs or successful inference.

## Palette and typography

Charcoal background #101419; panel #1A212A; card #222C36; border #394656; ivory text #F5F0E3; steel secondary text #AEBBC7; orange primary action #FF6B1A with dark #14100B text. Suggested semantic accents: green #7DD3A8, amber #FFC46B and red #FF9B8E. Never convey an error through color alone. The model supplied contrast estimates; they are not treated as independently verified measurements.

Use system sans-serif text and monospace for evidence labels. Suggested base: 15px with 1.5 line height; small uppercase instrument labels with 0.08em spacing. Visible focus outlines, minimum 44px targets and reduced-motion support.

## Layout

At 390px, use one column with 16px margins: identity and model state, source selector, full-width action, inventory, trust boundaries and evidence. At 1440px, the model suggested a three-column instrument rack. The implementation keeps the existing navigation and a two-column inventory/boundary area for simpler reading; evidence spans the workspace below.

Demo cards use a striped mode banner and a conspicuous SIMULATED badge. USB uses a solid banner and an explicit authorization state. Runtime model status must never imply that development design assistance is active product inference.

## English labels

Source selector: Simulated demo / Android USB. Actions: Refresh demo / List USB devices / Inspect evidence. Banners: SIMULATED / DEMO and USB / READ-ONLY. Inventory states: no device detected, unauthorized, offline and authorized. Evidence is labeled by source; hardware writes and Undo remain unavailable.

The model recommended restricting USB display to authorization and interface facts. The implementation uses the participant-authorized read-only device facts required by the project, while excluding serial numbers, network identifiers and private account content. This is a deliberate scope adaptation.

## Failure and safety states

Offline devices provide reconnection guidance. Unauthorized devices explain the Android consent step. Never automatically retry permission or model calls. Do not label a completed inventory as a successful model inference. Keep development assistance separate from shipped runtime inference.
