"""Back-compat wrapper: builds the ARTIFACT B jury evidence package.

Same CLI as before (--out, --evidence-dir, --test-results). For the full
three-artifact builder see scripts/release_pack.py (app/evidence/media).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_pack import main as release_main


def main():
    argv = ['evidence']
    raw = sys.argv[1:]
    if '--out' not in raw:
        argv += ['--out', 'E:/OpenBridge-Jury-Release.zip']
    release_main(argv + raw)


if __name__ == '__main__':
    main()
