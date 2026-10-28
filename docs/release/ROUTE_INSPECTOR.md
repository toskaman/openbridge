# Read-only route inspector — 28 October 2026

The Learned Skills workspace now has an explicit route-evidence refresh for the accepted B2rev2 response. It requests only GET /api/v2/skill_routes?skill=, performs no discovery, does not infer route readiness from the catalog, and offers no invocation, provider-policy or consent-writing action. Backend absence is displayed honestly; this does not implement the missing routing endpoint.

Rendering distinguishes backend eligibility, selection, invocation status, consent, freshness and evidence. SIMULATED remains visible. A structural consumer guard refuses unsupported versions, invalid display fields, unknown states/evidence/reasons and mismatched skills. It is not a replacement for the full backend JSON Schema/semantic validator or execution authorization. Older sequence values in the same epoch are refused; changing the skill invalidates an older request's display. The panel is a manually refreshed snapshot, not automatic live polling or a failover controller.

The failed-first browser test initially found the refresh control absent. Controlled tests now cover the shared BLE-route and empty fixtures, lower graph revisions, SIMULATED labels, unknown schema version, 404 backend absence and GET-only behavior at390/768/1440/3440. They use mocked route responses; simulated fixtures containing REAL_HARDWARE labels are not physical proof. No real device/model requests occur in this test.

Claude's main theme remains. Next: runtime B2 implementation, then live backend/consumer integration and independently recorded physical failover. The owner's order remains routing, hardware failover, then supported multi-PC review. There is no scheduled follow-up and no video work.
