"""Throwaway Frontier-30 staging gates. Delete after integration."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def gate_yaml():
    import yaml
    doc = yaml.safe_load((ROOT / ".github/workflows/android.yml").read_text(encoding="utf-8"))
    jobs = sorted(doc.get("jobs", {}).keys())
    assert jobs == ["build-apk", "e2e", "phone", "tv", "wear"], jobs
    phone = doc["jobs"]["phone"]
    runs = "\n".join(str(s.get("run", "")) + "\n" + str((s.get("with") or {}).get("script", "")) for s in phone.get("steps", []))
    for marker in ("wait-for-device", "pidof", "phone-logcat.txt"):
        assert marker in runs, marker
    print("YAML-GATE OK jobs=%s wait+retry+diag present" % jobs)


def gate_manifest():
    data = json.loads((ROOT / "docs/jury/MEDIA_MANIFEST_V2.json").read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else data.get("entries", data.get("media", []))
    assert len(entries) == 14, len(entries)
    blob = json.dumps(entries)
    assert "wd7-direct-drain-tv-adb-down" in blob
    print("MANIFEST-GATE OK entries=14 wd7-present")


def gate_png():
    from PIL import Image
    p = ROOT / "docs/jury/screens/tv-wd7-direct-drain-caption.png"
    with Image.open(p) as im:
        im.verify()
    assert p.stat().st_size == 220411, p.stat().st_size
    print("PNG-GATE OK 220411B verified")


def gate_counts():
    targets = {
        "README.md": ["30 verified evidence rows", "(30 VERIFIED rows)"],
        "docs/KNOWN_LIMITATIONS.md": ["30 rows, all VERIFIED", "21 REAL_HARDWARE"],
        "docs/RELEASE_STATUS.md": ["30 VERIFIED rows", "(30 VERIFIED rows)"],
        "docs/jury/JURY_START_HERE.md": ["30 verified evidence rows", "30 rows"],
        "docs/jury/VERIFIED_CAPABILITIES.md": ["(30 rows", "21 REAL_HARDWARE"],
        "docs/release/SUBMISSION_EVIDENCE.md": ["30 VERIFIED rows"],
    }
    bad = []
    for rel, needles in targets.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for n in needles:
            if n in text:
                bad.append("%s :: %r" % (rel, n))
    assert not bad, bad
    print("COUNTS-GATE OK no stale 30/21 in 6 files")


def gate_bare_read():
    bad = []
    for path in list(ROOT.glob("src/**/*.py")) + list(ROOT.glob("tests/**/*.py")) + list(ROOT.glob("dev/*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            s = line.strip()
            if not re.search(r"\.(read_text|write_text)\s*\(", s) and "open(" not in s:
                continue
            window = "\n".join(lines[i:i + 5])
            if "encoding" in window or '"xb"' in window or "'xb'" in window or "PIPE" in window or "urlopen" in window:
                continue
            if re.search(r"\.read_text\(\s*\)", s):
                bad.append("%s:%d" % (path.relative_to(ROOT), i + 1))
            elif re.search(r"\.write_text\(", s) and "encoding" not in window:
                bad.append("%s:%d" % (path.relative_to(ROOT), i + 1))
            elif "open(" in s and re.search(r"open\([^)]*'w'", s) and "encoding" not in window:
                bad.append("%s:%d" % (path.relative_to(ROOT), i + 1))
    assert not bad, bad[:20]
    print("BAREIO-GATE OK zero bare text IO in src/tests/dev")


def gate_coverage():
    text = (ROOT / "docs/jury/CLAIM_EVIDENCE_MATRIX.md").read_text(encoding="utf-8")
    covered = set()
    for m in re.finditer(r"[Rr]egistry rows?\s+(\d+)(?:\s*[-\u2013]\s*(\d+))?", text):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        covered.update(range(a, b + 1))
    for m in re.finditer(r"\(facts \+ seek accepted, row (\d+)\)", text):
        covered.add(int(m.group(1)))
    missing = sorted(set(range(18, 36)) - covered)
    assert not missing, missing
    print("COVERAGE-GATE OK covered [18..35]")


GATES = {"yaml": gate_yaml, "manifest": gate_manifest, "png": gate_png,
         "counts": gate_counts, "bareio": gate_bare_read, "coverage": gate_coverage}

if __name__ == "__main__":
    for name in sys.argv[1:]:
        GATES[name]()
