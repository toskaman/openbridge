"""Build libobai.so (AI on the phone: llama.cpp + whisper.cpp + the Companion's JNI layer) for arm64 phones.

    python -m dev.build_companion_ai                          # sources and build folder under D:\\OpenBridgeAI
    OB_AI_SRC=<folder with llama.cpp and whisper.cpp> python -m dev.build_companion_ai

Needs the Android NDK (sdkmanager "ndk;27.2.12479018"), CMake and Ninja. The library lands in
<OB_AI_SRC>/build/arm64-v8a/libobai.so; `python -m dev.build_companion` puts it in the APK when it is there
(OB_AI_LIB overrides the path). The two engines are MIT-licensed and are not vendored in this repository.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

SDK = Path(os.environ.get('ANDROID_SDK_ROOT', os.environ.get('ANDROID_HOME', r'D:\Android\sdk')))
NDK_VERSION = '27.2.12479018'
SRC = Path(os.environ.get('OB_AI_SRC', r'D:\OpenBridgeAI'))
NATIVE = Path(__file__).resolve().parent.parent / 'companion' / 'android' / 'native'
ABI, API = 'arm64-v8a', 26
# Helio G99 class (Cortex-A76 / A55): dot product and fp16 arithmetic.
ARM_ARCH = os.environ.get('OB_AI_ARM_ARCH', 'armv8.2-a+dotprod+fp16')


def lib_path():
    return Path(os.environ.get('OB_AI_LIB') or SRC / 'build' / ABI / 'libobai.so')


def main():
    ndk = SDK / 'ndk' / NDK_VERSION
    if not (ndk / 'build' / 'cmake' / 'android.toolchain.cmake').exists():
        sys.exit('FAILED: Android NDK %s not found under %s (sdkmanager "ndk;%s")' % (NDK_VERSION, SDK / 'ndk', NDK_VERSION))
    for d in ('llama.cpp', 'whisper.cpp'):
        if not (SRC / d / 'CMakeLists.txt').exists():
            sys.exit('FAILED: %s missing (git clone https://github.com/ggml-org/%s into %s)' % (SRC / d, d, SRC))
    build = SRC / 'build' / ('cmake-' + ABI)
    cfg = ['cmake', '-S', str(NATIVE), '-B', str(build), '-G', 'Ninja',
           '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build' / 'cmake' / 'android.toolchain.cmake'),
           '-DANDROID_ABI=' + ABI, '-DANDROID_PLATFORM=android-%d' % API, '-DANDROID_STL=c++_static',
           '-DCMAKE_BUILD_TYPE=Release', '-DGGML_CPU_ARM_ARCH=' + ARM_ARCH,
           '-DOB_LLAMA_DIR=' + str(SRC / 'llama.cpp'), '-DOB_WHISPER_DIR=' + str(SRC / 'whisper.cpp')]
    for cmd in (cfg, ['cmake', '--build', str(build), '--target', 'obai', '-j', str(os.cpu_count() or 4)]):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.exit('FAILED %s:\n%s\n%s' % (cmd[1], r.stdout[-4000:], r.stderr[-4000:]))
    out = lib_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    strip = next((ndk / 'toolchains' / 'llvm' / 'prebuilt').glob('*/bin/llvm-strip*'))
    shutil.copy2(build / 'libobai.so', out)
    subprocess.run([str(strip), '--strip-unneeded', str(out)], check=True)
    print('LIB', out, out.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
