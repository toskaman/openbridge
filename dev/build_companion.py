"""Reproducible build of the OpenBridge Companion APK with the official Android SDK tools only (no Gradle, no libraries).
Signing key: generated once under %LOCALAPPDATA%/OpenBridge/companion-signing (never in Git).

    python -m dev.build_companion                       # the normal APK
    python -m dev.build_companion --software-rendering  # test build for the PICO OS 6 emulator only (docs/PICO_EMULATOR.md):
                                                        # its x86_64 image crashes hardware-accelerated third-party apps
"""
import os, shutil, subprocess, sys, zipfile, hashlib
from pathlib import Path

SDK = Path(os.environ.get('ANDROID_SDK_ROOT', os.environ.get('ANDROID_HOME', r'D:\Android\sdk')))
BT = SDK / 'build-tools' / '34.0.0'
BAT = '.bat' if os.name == 'nt' else ''      # SDK wrappers: d8/apksigner are .bat on Windows, bare ELF scripts elsewhere
EXE = '.exe' if os.name == 'nt' else ''      # aapt2/zipalign are .exe on Windows, bare ELF elsewhere
JAR = SDK / 'platforms' / 'android-34' / 'android.jar'
SRC = Path('companion/android')
# OB_BUILD_DIR: build somewhere local when the checkout sits on a network share (javac can fail writing classes there).
OUT = Path(os.environ.get('OB_BUILD_DIR', 'artifacts/companion'))


def run(*args):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, shell=str(args[0]).endswith('.bat'))
    if r.returncode:
        sys.exit(f'FAILED {Path(str(args[0])).name}:\n{r.stdout}\n{r.stderr}')
    return r.stdout


def main(argv=None):
    software = '--software-rendering' in (sys.argv[1:] if argv is None else argv)
    shutil.rmtree(OUT, ignore_errors=True); (OUT / 'classes').mkdir(parents=True)
    manifest = SRC / 'AndroidManifest.xml'
    if software:
        text = manifest.read_text(encoding='utf-8')
        if '<application ' not in text:
            sys.exit('FAILED: no <application> tag in the manifest')
        manifest = OUT / 'AndroidManifest.xml'
        manifest.write_text(text.replace('<application ', '<application android:hardwareAccelerated="false" ', 1), encoding='utf-8')
    sources = sorted(str(p) for p in (SRC / 'src').rglob('*.java'))
    run('javac', '-encoding', 'UTF-8', '--release', '11', '-Xlint:-options', '-classpath', JAR, '-d', OUT / 'classes', *sources)
    classes = sorted(str(p) for p in (OUT / 'classes').rglob('*.class'))
    run(BT / ('d8' + BAT), '--release', '--min-api', '26', '--lib', JAR, '--output', OUT, *classes)
    res = SRC / 'res'
    link_args = ['link', '--manifest', manifest, '-I', JAR, '-o', OUT / 'base.apk']
    if res.is_dir():
        run(BT / ('aapt2' + EXE), 'compile', '--dir', res, '-o', OUT / 'res.zip')
        # -R archives get overlay treatment in build-tools 34: auto-add our base resources.
        link_args += ['-R', OUT / 'res.zip', '--auto-add-overlay']
    run(BT / ('aapt2' + EXE), *link_args)
    with zipfile.ZipFile(OUT / 'base.apk', 'a') as z:
        z.write(OUT / 'classes.dex', 'classes.dex')
        # AI on the phone (optional): libobai.so from `python -m dev.build_companion_ai`; without it the AI page says
        # the engine is not in this build and everything else works the same.
        from dev.build_companion_ai import lib_path
        if lib_path().exists():
            z.write(lib_path(), 'lib/arm64-v8a/libobai.so')
            print('AI engine included:', lib_path(), lib_path().stat().st_size, 'bytes')
    run(BT / ('zipalign' + EXE), '-f', '-p', '4', OUT / 'base.apk', OUT / 'aligned.apk')
    keydir = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'OpenBridge' / 'companion-signing'
    keystore = keydir / 'companion.jks'
    if not keystore.exists():
        keydir.mkdir(parents=True, exist_ok=True)
        pw = os.urandom(18).hex(); (keydir / 'pass.txt').write_text(pw, encoding='utf-8')
        run('keytool', '-genkeypair', '-keystore', keystore, '-storepass', pw, '-keypass', pw, '-alias', 'openbridge',
            '-keyalg', 'RSA', '-keysize', '3072', '-validity', '3650', '-dname', 'CN=OpenBridge Companion (participant build)')
    pw = (keydir / 'pass.txt').read_text(encoding='utf-8').strip()
    apk = OUT / ('openbridge-companion-software-rendering.apk' if software else 'openbridge-companion.apk')
    run(BT / ('apksigner' + BAT), 'sign', '--ks', keystore, '--ks-pass', 'pass:' + pw, '--out', apk, OUT / 'aligned.apk')
    print(run(BT / ('apksigner' + BAT), 'verify', '--print-certs', apk).splitlines()[0])
    print('APK', apk, apk.stat().st_size, 'bytes sha256', hashlib.sha256(apk.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
