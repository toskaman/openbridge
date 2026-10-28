"""Meta-generated skill implementation (ONE P0 capability, §8 provenance).

- goal: read-only fabric status summary (no hardware, no permissions, idempotent)
- model: llama3.2:3b-instruct-q4_K_M (local Ollama 127.0.0.1:11437, digest-pinned service)
- generated: 2026-10-28, attempt 1 (Llama; Glimmer /api/chat returned HTTP 500, tags-only)
- generation: 18.6 s, 152 eval tokens, temperature 0, JSON-schema pinned ({code})
- code_sha256: dbf1ba66b7912bb4864fa7d8c409b9f9b382928e059d17ff1c009a49ed867cfb
- validation: AST parse OK, zero imports, no open/eval/exec/compile/__import__;
  executed in a restricted-builtins sandbox against the contract vectors PASS;
  tests/runtime/test_command_center.py (purity + behavior) PASS
- review: deterministic validator + test suite (no human edits to the generated body)
- status: VERIFIED (unit + sandbox + live approve/execute READ over seeded registry)
"""


def summarize(devices, relays):
    devices_total = len(devices)
    by_category = {}
    relays_total = len(relays)
    relays_online = sum(1 for relay in relays.values() if relay.get('online', False))
    for device in devices.values():
        category = device.get('category', 'unknown')
        if category not in by_category:
            by_category[category] = 0
        by_category[category] += 1
    return {'devices_total': devices_total, 'by_category': by_category, 'relays_total': relays_total, 'relays_online': relays_online}
