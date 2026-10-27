# Active work constraints

Owner instruction, 27 October 2026: **do not generate videos until the entire project is complete**. Recording, editing, rendering and new video publication are paused. Existing artifacts remain historical; do not run the video helpers during ongoing product work.

Continue product implementation, runtime integration, safety/contract tests, browser checks and evidence. Keep all content English. Do not edit the runtime owner's protected backend, hardware, Companion, permission or recovery files. Keep main unchanged pending integration validation.

The runtime owner has now recorded the authenticated phone-relay HTTP lifecycle in b5f1ab8 (publish/read 200, denied after relay revocation, removed route 404). Remaining gates include final runtime integration, the TV/inaccessible-device scenario, stronger composition evaluation and the remaining requested product features. A successful synthetic Glimmer proposal does not mark these gates complete.

Latest controlled integration: runtime 6231b0e plus current Forge overlay passes 266 unit/integration tests and six browser modules, with the self-tested I/O guard recording zero forbidden attempts. See cross-branch-current-test-receipt.json. These are controlled tests, not new hardware or model evidence. Two runtime fixture HTTPError cleanup warnings remain. The injected-source path label is now tested through planning.
