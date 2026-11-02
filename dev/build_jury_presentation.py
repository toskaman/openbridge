"""Build the jury presentation ZIP reproducibly.

Usage: python dev/build_jury_presentation.py [--without-extras]
Stages a trimmed repo subtree (repo-relative layout preserved so every
relative link keeps working), validates link targets, zips it, and writes a
SHA-256 manifest. Never published automatically (owner-gated).

STAGE/ZIP default to E:/jury-pack (author PC, where the 10 MB mp4 lives);
override with JURY_PACK_STAGE / JURY_PACK_ZIP. --without-extras skips
outside-repo extras (warns, still exits 0) for machines without E:.
"""

import hashlib
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = Path(os.environ.get("JURY_PACK_STAGE", "E:/jury-pack/OpenBridge-Jury-Presentation"))
ZIP = Path(os.environ.get("JURY_PACK_ZIP", str(STAGE.parent / "OpenBridge-Jury-Presentation.zip")))

LINK = re.compile(r"\[[^\]]*\]\(([^)#]+)(?:#[^)]*)?\)")
HTML_LINK = re.compile(r"""(?:href|src)=["']([^"'#]+)(?:#[^"']*)?["']""")

# (repo glob, keep in stage) — globs relative to ROOT.
INCLUDE = [
    "README.md",
    "EVIDENCE_LEDGER.md",
    "CONTRIBUTIONS.md",
    "THIRD_PARTY.md",
    "LICENSE",
    "DEVICE_SCOPE.md",
    "RISK_REGISTER.md",
    "docs/*.md",
    "docs/*.json",
    "docs/jury/*.md",
    "docs/jury/*.json",
    "docs/jury/screens/*",
    "docs/showcase/*",
    "docs/evidence/*.md",
    "docs/release/*.md",
    "docs/release/*.json",
    "docs/release/failover-evidence/*",
    "docs/forge/*.md",
    "docs/forge/*.json",
    "docs/forge/workspace-evidence/*.json",
    "docs/forge/evaluation-v2/RESULTS.md",
    "docs/forge/evaluation-v2/results/*",
    "docs/evaluation/routing-v1/*",
    "docs/evaluation/routing-v1/results/*",
    "docs/evaluation/routing-v1/explain/*",
    "docs/evidence/v4/**/*.md",
    "src/runtime/command.py",
    "tests/e2e/command_center_smoke.py",
    "tests/fabric/test_capability_explorer.py",
    "docs/benchmark/STATUS.md",
    "docs/benchmark/EVAL_1000_RULES_BASELINE.md",
    "docs/benchmark/EVAL_SUBSET_50_LOCAL.md",
    "docs/benchmark/advisor-benchmark-glimmer.json",
    "docs/benchmark/agent-benchmark-glimmer.json",
    "docs/benchmark/agent-benchmark-llama3b.json",
    "docs/benchmark/v4/REGISTRATION.md",
    "docs/benchmark/v4/ablation-*.json",
    "docs/api/HTTP.md",
    "docs/contracts/B2_SKILL_ROUTING_CONTRACT.md",
    "docs/coordination/DEVICE_CAPABILITY_CONTRACT_V1.md",
    "docs/runtime/PERSISTENCE.md",
    "docs/safety/BOUNDARIES.md",
    "docs/safety/FREE_CREDITS.md",
    "docs/evaluation/routing-v1/RESULTS.md",
    "docs/evaluation/routing-v1/explain/FREEZE_GUIDE.md",
    "docs/archive/RELEASE_CHECKPOINTS.md",
    "docs/archive/README_2026-10-31.md",
    "src/ai/registry.py",
    "src/ai/glimmer.py",
    "src/ai/local_meta.py",
    "src/ai/router.py",
    "src/runtime/nl_router.py",
    "config/runtime_models.json",
    "artifacts/s5-tv-panel-31oct/t2-propose-medium.json",
    "artifacts/s5-tv-panel-31oct/chain-transcript.json",
    "scripts/verify/companion_toggle_check.py",
    "companion/android/src/fr/openbridge/companion/MainActivity.java",
    "companion/android/src/fr/openbridge/companion/RelayService.java",
    "dev/s5b_safe_seek_chain.py",
    "dev/s5_tv_panel_chain.py",
    "dev/device_registry.py",
    # Pack-completeness (Nov 2026): files the staged docs link to.
    "HACKATHON_EVALUATION_PERMISSION.md",
    "docs/ui/**/*",
    "docs/benchmark/**/*",
    "docs/superpowers/**/*",
    "scripts/verify/cloud_e2e.py",
    "src/runtime/command_drain.py",
]

OPTIONAL = {
    "artifacts/s5-tv-panel-31oct/chain-transcript.json",
    # t2-propose was never committed either (artifacts/ is gitignored);
    # same honest treatment as the chain transcript (Nov 2026).
    "artifacts/s5-tv-panel-31oct/t2-propose-medium.json",
}

# Archived snapshots keep root-relative links by design; their own link
# targets are not validated (they resolve at repo root, not in the pack).
VALIDATE_SKIP = {
    "docs/archive/README_2026-10-31.md",
}

EXTRAS = [  # (outside-repo source, stage path)
    ("E:/shots/phone-scan-live.mp4", "assets/phone-scan-live.mp4"),
]

INDEX = """# OpenBridge jury presentation pack

Built from branch `feat/jury-presentation-redesign` by
`python dev/build_jury_presentation.py`. Layout mirrors the repository so
every relative link validates. Start at `docs/jury/JURY_START_HERE.md`.

Suggested reading map: README.md (pitch) → docs/jury/JURY_START_HERE.md
(judge fast-track) → docs/QUICKSTART.md (run it) →
docs/UNIVERSAL_DEVICE_ARCHITECTURE.md (design) →
docs/jury/VERIFIED_CAPABILITIES.md (verdicts) → docs/RELEASE_EVIDENCE.md
(index) → docs/KNOWN_LIMITATIONS.md (limits) →
docs/jury/COMPLIANCE_CHECKLIST.md (hackathon gates) →
docs/jury/DEMO_STORYBOARD_FINAL.md + DEMO_NARRATION.md +
VIDEO_CAPTURE_CHECKLIST.md (video) → docs/jury/MEDIA_MANIFEST.md (shots).

`assets/phone-scan-live.mp4` is the 10 MB BLE-live clip (not in git).
The pre-redesign README snapshot (`docs/archive/README_2026-10-31.md`) keeps
root-relative links by design (validated at repo root, not in-pack).
SHA-256 per file: SHA256SUMS.txt.
"""


def main():
    skip_extras = "--without-extras" in sys.argv[1:]
    if STAGE.exists():
        shutil.rmtree(STAGE)
    copied, missing = 0, []
    for pattern in INCLUDE:
        hits = sorted(ROOT.glob(pattern))
        if not hits and pattern not in OPTIONAL and "*" not in pattern:
            missing.append(pattern)
        for src in hits:
            if not src.is_file():
                continue
            dest = STAGE / src.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            copied += 1
    skipped = []
    for src, rel in EXTRAS:
        src = Path(src)
        if skip_extras:
            skipped.append(str(src))
            continue
        if not src.is_file():
            missing.append(str(src))
            continue
        dest = STAGE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        copied += 1
    index = INDEX
    if skipped:
        index += "\nSkipped extras (--without-extras):\n" + "".join("- %s\n" % s for s in skipped)
    (STAGE / "ZIP_INDEX.md").write_text(index, encoding="utf8")

    broken = []
    docs = [(md, LINK) for md in STAGE.rglob("*.md")]
    docs += [(md, HTML_LINK) for md in STAGE.rglob("*.html")]
    for md, pattern in docs:
        if md.relative_to(STAGE).as_posix() in VALIDATE_SKIP:
            continue
        for target in pattern.findall(md.read_text(encoding="utf8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (md.parent / target).exists():
                broken.append("%s -> %s" % (md.relative_to(STAGE), target))

    sums = []
    for path in sorted(STAGE.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            sums.append("%s  %s" % (digest, path.relative_to(STAGE).as_posix()))
    (STAGE / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf8")

    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(STAGE.rglob("*")):
            if path.is_file():
                archive.write(path, "OpenBridge-Jury-Presentation/" + path.relative_to(STAGE).as_posix())
    print("staged %d files, zip %d bytes" % (copied, ZIP.stat().st_size))
    print("zip sha256 %s" % hashlib.sha256(ZIP.read_bytes()).hexdigest())
    for item in skipped:
        print("SKIP-EXTRA " + item)
    for item in missing:
        print("MISSING " + item)
    for item in broken:
        print("BROKEN-LINK " + item)
    return 0 if not missing and not broken else 1


if __name__ == "__main__":
    sys.exit(main())
