# Live routing integration — 28 October 2026

Combines Claude PR49 runtime with the read-only inspector on main. Four typed skills and CSRF-protected policy/arm/invoke endpoints use the accepted B2rev2 contract, existing Executor and deterministic authorization. Contract acceptance alone was not this implementation; this is its separately tested integration.

Two failed-first integration regressions reproduced completed-retry target mismatch and concurrent lazy router creation. Completed retry fingerprints now include the requested target, and initialization is serialized. One invocation cannot reuse a cached result for another requested target. These tests use synthetic devices and fake runners, not real action execution.

The inspector now supports selecting an existing discovered device for targeted skills, adds target to the GET request, checks selected-route target matching, and scopes stored graph revisions by skill and target. It remains read-only and manually refreshed; it does not provide policy controls or invoke actions.

Validation: 484 unit/integration tests passed after backend fixes;15 routing tests passed; extended inspector browser fixture checks passed at390/768/1440/3440, including target selection. Compileall, theme-source check and diff check passed. Physical TV-to-phone proof is still outstanding: ADB showed one authorized device and no usable TV endpoint at readiness inspection. No broad scan or device action was made during the check. Owner requested TV readiness asynchronously.

Next: final CI/merge, safely reload the owned local service after recovery inspection, verify actual endpoints, then pair authorized TV/phone Companions and collect new scan provenance after TV loss. PINNED refusal and missing-provider cases must remain distinct. Automatic retry is permitted only where runtime policy/implementation actually support it; manual provider re-selection is not universal transparent failover. Multi-PC review follows that physical stage, with no scheduled automation or retry of the earlier safety-blocked port. No videos or new hosted model calls.
