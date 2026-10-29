# UI layout v2 — contract for Meta-generated UIViewPlans (additive to obv4.1)

Owner: Claude (renderer, binding, enforcement). Consumer/author: Muse (which widgets, labels, layout).

## UIViewPlan widget kinds
| kind | binding | extra | device behaviour | PC enforcement |
|---|---|---|---|---|
| `button` | required (manifest_hash + inputs) | — | hold to send | grant re-checked per press |
| `confirm` | required | — | hold, then a Confirm/Run dialog | a press without `gesture: confirm` is BLOCKED |
| `status` | must be `null` | `source`: widget_id of a button/confirm | shows the source's last outcome (`done 14:54`, `blocked 14:55`) | never executes; value pushed by the PC |
| `label` | must be `null` | — | text only | never executes |

Rules checked by `Substrate.install_ui_plan`: unique `widget_id`; `source` only on `status` and it must name an action
widget; labels/status cannot bind; ≤ 12 widgets; injection checks on every label; each action binding compiles and its
owner grant is verified. `layout_version` becomes the relay `revision`.

## Relay protocol (openbridge-relay/1, additive)
- `set_controls {controls: [{control_id, label[, kind][, value]}], revision?}` — replaces the layout and clears pending presses.
- `update_status {values: {control_id: text<=40}}` — status values only; pending presses are kept.
- `get_requests` reply may carry `applied_revision` = the revision the screen actually rendered (device ACK).
- `GET /api/v2/remote_controls` → `layouts[relay_id] = {revision, acked, display[]}`.

## Lifecycle guarantees (tested; hardware run in docs/evidence/v4/ui-v2)
Persisted on the device across app restarts; revocation of the grant blocks execution even though the widget is still
drawn; clearing controls removes them; an offline relay is re-probed every 5 s; presses older than 30 s never run.
Old Companions (≤0.7) ignore `kind` and render every control as a button: send v2 plans only to ≥0.8.
