"""Live TV verification: tv_sleep -> oracle -> tv_wake -> oracle -> companion_foreground -> oracle.

Usage: python -m dev.tv_sleep_verify 'android tv'
Resolves the TV key from discovery, executes the 3 skills with owner consent,
records every receipt + oracle read into E:/shots/tv-sleep-02nov/tv-sleep-transcript.json.
Owner watches the TV go dark, wake, and show the Companion. No presses injected.
"""
import json
import sys
import time
from argparse import Namespace
from pathlib import Path

OUT = Path("E:/shots/tv-sleep-02nov")
OUT.mkdir(parents=True, exist_ok=True)

from src.server import create_server  # noqa: E402
from src.cli import ensure_discovery, default_providers  # noqa: E402
from src.runtime.primitives import Executor  # noqa: E402

LABEL = sys.argv[1] if len(sys.argv) > 1 else "android tv"
SKILLS = tuple(sys.argv[2:]) or ("tv_sleep", "tv_wake", "companion_foreground")


def main():
    out = {"label": LABEL, "steps": []}
    s = create_server(0)
    snap = ensure_discovery(s, default_providers(Namespace(providers=None)))
    devs = [d for d in snap.get("devices", []) if d.get("label") == LABEL]
    if not devs:
        raise SystemExit("TV label %r not discovered" % LABEL)
    key = devs[0]["key"]
    ex = Executor(s)
    for skill in SKILLS:
        r = ex.execute(skill, key, {}, True)
        out["steps"].append({"skill": skill, "state": r["state"],
                             "verified": r.get("verified"), "result": r.get("result"),
                             "errors": r.get("errors")})
        print(skill, "->", r["state"], "verified=%s" % r.get("verified"), flush=True)
        time.sleep(3)
    (OUT / "tv-sleep-transcript.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    if any(st["state"] != "EXECUTED" or not st["verified"] for st in out["steps"]):
        raise SystemExit("LIVE RUN FAILED — see transcript")
    print("LIVE RUN PASS", flush=True)


if __name__ == "__main__":
    main()
