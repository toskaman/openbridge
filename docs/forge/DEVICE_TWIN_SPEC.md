# Device Digital Twin projection

The Forge preview presents three separate nodes: local workspace, relay and observed device. Fixture labels are human-friendly UI text; opaque device_id and relay_id are the API identity. Source, simulation status, evidence references, observation time, grants, availability and supported operations remain explicit.

This is a projection for read-only capability publication, not a new hardware registry. Device Fabric owns canonical identity, strong identifier merging, permissions and discovery. Integration must project the final DEVICE_CAPABILITY_CONTRACT_V1 into the Forge manifest without upgrading weak identity or inferred capabilities.

The path means “workspace reads observations reported through this relay,” not “workspace directly controls the beacon.” Contradictory identity is unavailable. Multiple routes are candidate alternatives, not proof that two identifiers represent the same physical device. Manufacturer bytes remain raw data; unsupported semantic measurements stay unavailable.

Files: src/forge/ui and fixtures.py; source boundary in service.py. Tests include identity conflict, absent device and changed provenance. The current cards are simulated and do not claim live device synchronization.
