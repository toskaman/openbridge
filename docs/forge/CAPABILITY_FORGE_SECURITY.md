# Capability Forge security

Trust enters through a trusted server-side CapabilityProvider, never model output or caller claims. A manifest is structural data and is not itself proof of authority. Integration must reread the existing permission registry and authenticated relay evidence for each snapshot. The Forge does not replace relay HMAC validation, the authorization registry, or transaction recovery.

Only read_observations and internal publish_readonly are recognized. No shell, ADB, URL, dynamic import, eval, exec or model-generated code dispatch exists. The exported Python client is a fixed template with validated path identifiers. No generated code is executed by the service. An RSSI/name/manufacturer advertisement does not establish temperature, battery, ownership or control.

Binding covers version, service, capability, device, relay, source, status, simulation and operation. Fresh data can change, but a route cannot silently change its provenance. Future timestamps and observations older than their bounded maximum age are rejected. Missing grants, removed devices, offline relays and identity conflicts fail closed. Simulated and physical verification statuses cannot be interchanged.

The demo binds to numeric loopback, validates Host exactly and requires an ephemeral bearer for data. Mutation additionally requires exact Origin. Browser CSP forbids external resources and framing; responses are non-cacheable. Input is bounded. This is a trusted single-user development host, not a multi-user Internet service. A local user/process with equal OS rights is outside this browser-origin boundary.

Concurrent reads and revocation share a lock. Audit history omits tokens and observation contents, is bounded and in-memory; it is not a durable security journal. No automatic hardware scan or write occurs. No Undo integration is needed for read-only publication. Write-capable composition is deliberately unavailable until the core policy and transaction contract covers it.

Tests cover denied permissions, expiry, forged provenance, removed devices, invalid models, invented IDs, consent bypass and concurrent publication. Trusted injected-provider integration is proven on physical phone and TV relays, including the [combined TV/Glimmer journey](TV_GLIMMER_JOURNEY.md). Normal product entrypoint integration and independent threat review remain outstanding.
