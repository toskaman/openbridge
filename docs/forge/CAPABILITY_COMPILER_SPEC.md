# Capability compiler specification

Version 1 is strict: exact fields only, no extensions. See the runnable fixture in src/forge/fixtures.py. Identifiers match [a-z][a-z0-9_.-]{0,63}. The only operation is read_observations. Source must exactly equal RELAY:<relay_id>. Verified must be true. Status must be SIMULATED_VERIFIED with simulation=true, or REAL_HARDWARE_VERIFIED with simulation=false. These assertions must originate from the trusted provider.

Permissions are a duplicate-free subset of observe/read; both are required at runtime. Availability, device_present and identity_conflict are exact booleans. observed_at is finite Unix seconds. max_age_seconds is an integer from 1 to 300. Evidence references are 1–32 unique validated IDs. Observations number 1–200 and require unique observation_id and an integer rssi_dbm from -127 to 20. Optional name is bounded to 60 printable characters; optional manufacturer_data_hex is at most 64 raw bytes represented as lowercase hex. No other measurement is accepted.

compile_manifest returns openapi, schemas, python_client, documentation and manifest_sha256. Identical structured input gives identical output. The hash uses sorted compact JSON. Exported schemas resolve their own local $defs; OpenAPI components use component references. The contract documents bearer authentication, errors and fixed GET operations. The client uses numeric loopback and rejects proxy forwarding/redirects.

Tests: deterministic output, correct route, Python syntax, standalone schema validation when optional jsonschema is installed, malformed inputs and absence of invented temperature fields. No model is involved in compilation.
