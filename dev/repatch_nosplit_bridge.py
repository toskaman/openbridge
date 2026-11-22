"""
Re-patch the already de-split ActiveLook APK with the current OpenBridge bridge (PATCH_JS v3+),
then zipalign + sign it. Keeps the merged manifest/splits fix of ActiveLook-OpenBridge-NoSplit.apk.

    python dev\\repatch_nosplit_bridge.py            -> ActiveLook-OpenBridge-NoSplit-v6.apk
    python dev\\repatch_nosplit_bridge.py --check     -> patch bundle.js only, no signing (any OS)
"""
import pathlib
import subprocess
import sys
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent                      # Z:\\Hackatons\\OpenBridge
SRC = ROOT / "ActiveLook-OpenBridge-NoSplit.apk"
UNALIGNED = ROOT / "ActiveLook-OpenBridge-NoSplit-v6.unaligned.apk"
ALIGNED = ROOT / "ActiveLook-OpenBridge-NoSplit-v6.aligned.apk"
OUT = ROOT / "ActiveLook-OpenBridge-NoSplit-v6.apk"
START = "// --- OPENBRIDGE EMULATOR BRIDGE START ---"
END = "// --- OPENBRIDGE EMULATOR BRIDGE END ---"


def load_patch_module(check_only: bool):
    src = (HERE / "build_activelook_openbridge.py").read_text(encoding="utf-8")
    if check_only:  # do not touch the keystore password outside Windows
        src = src.replace('PW = (KEYDIR / "pass.txt").read_text(encoding="utf-8").strip()', 'PW = ""')
        src = src.replace('KEYDIR = pathlib.Path(os.environ["LOCALAPPDATA"])', 'KEYDIR = pathlib.Path(".")')
    ns = {"__name__": "obpatch"}
    exec(compile(src, "build_activelook_openbridge.py", "exec"), ns)
    return ns


def patch_bundle(js: str, ns) -> str:
    a, b = js.find(START), js.find(END)
    if a < 0 or b < 0:
        raise RuntimeError("OpenBridge markers not found in bundle.js of " + SRC.name)
    new_block = ns["PATCH_JS"].strip("\n")
    js = js[:a] + new_block + js[b + len(END):]
    return ns["apply_extra_hooks"](ns["apply_serialized_hook"](js))


def main():
    check_only = "--check" in sys.argv
    ns = load_patch_module(check_only)
    with zipfile.ZipFile(SRC) as z:
        js = z.read("assets/app/bundle.js").decode("utf-8")
    js2 = patch_bundle(js, ns)
    assert "OpenBridgeOverlay" in js2 and "_frame(cmd, payload)" in js2 and "OB-SERIALIZED-EMULATOR\"&&" in js2
    print(f"[Repatch] bundle.js {len(js)} -> {len(js2)} chars")
    if check_only:
        (HERE / "bundle.v6.check.js").write_text(js2, encoding="utf-8")
        print("[Repatch] --check: wrote dev/bundle.v6.check.js (no APK built)")
        return

    with zipfile.ZipFile(SRC) as zin, zipfile.ZipFile(UNALIGNED, "w") as zout:
        for item in zin.infolist():
            name = item.filename
            if name.startswith("META-INF/") and (name.endswith((".SF", ".RSA", ".EC", ".DSA")) or name == "META-INF/MANIFEST.MF"):
                continue
            data = js2.encode("utf-8") if name == "assets/app/bundle.js" else zin.read(name)
            zout.writestr(item, data)

    sdk = ns["SDK"]
    subprocess.run([str(sdk / "zipalign.exe"), "-f", "-p", "4", str(UNALIGNED), str(ALIGNED)], check=True)
    subprocess.run([str(sdk / "apksigner.bat"), "sign", "--ks", str(ns["KEYSTORE"]), "--ks-pass", f"pass:{ns['PW']}",
                    "--out", str(OUT), str(ALIGNED)], check=True, shell=True)
    subprocess.run([str(sdk / "apksigner.bat"), "verify", str(OUT)], check=True, shell=True)
    print("[Repatch] SUCCESS ->", OUT)


if __name__ == "__main__":
    main()
