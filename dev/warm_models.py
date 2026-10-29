"""Pre-demo warm-up: load llama3b + MMS STT so the first live command is fast.

Zero production change: warms the pinned local endpoints. MMS warm runs in a
SUBPROCESS because transformers weight-loading can segfault the whole process
when free RAM is too low (needs ~6GB+; observed crash at 4.7GB free). A MMS
failure is reported honestly without killing the llama result.

Exit: 0 all warm, 2 partial (llama ok, MMS failed), 1 llama failed.
Safe to run any time; does not touch live 18765.

Usage:  python -m dev.warm_models
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, '.')

OB_ROOT = 'C:\\users\\TheBox\\Desktop\\Hackaton\\OpenBridge'
MMS_MIN_FREE_GB = 6.0


def free_ram_gb():
    try:
        import ctypes
        class MS(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                        ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                        ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                        ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                        ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
        ms = MS()
        ms.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        return ms.ullAvailPhys / 1e9
    except Exception:
        return -1.0


def main():
    os.chdir(OB_ROOT)
    t0 = time.monotonic()
    # 1. llama low tier: no-op chat keeps weights resident (keep_alive 10m in transport).
    from src.ai.local_meta import local_request
    try:
        r = local_request('/api/chat', {'model': 'llama3.2:3b-instruct-q4_K_M', 'stream': False,
                                        'keep_alive': '10m', 'messages': [{'role': 'user', 'content': 'ok'}]},
                          endpoint='http://127.0.0.1:11437', timeout=180)
        assert r.get('done'), r
        print(f'llama3b warm in {time.monotonic() - t0:.1f}s', flush=True)
    except Exception as e:
        print(f'LLAMA_WARM_FAILED: {type(e).__name__}: {e}', flush=True)
        return 1
    # 2. MMS STT in a subprocess (segfault isolation). Skip early if RAM is too low.
    free = free_ram_gb()
    print(f'free_ram_gb={free:.1f}', flush=True)
    if 0 <= free < MMS_MIN_FREE_GB:
        print(f'MMS_WARM_SKIPPED: need >={MMS_MIN_FREE_GB}GB free (close apps, retry)', flush=True)
        return 2
    t1 = time.monotonic()
    probe = ('import sys,numpy as np; sys.path.insert(0,\'.\'); '
             'from src.ai.stt_local import transcribe_pcm; '
             'transcribe_pcm((np.zeros(16000,dtype=np.int16)).tobytes(),\'fr\'); '
             'transcribe_pcm((np.zeros(16000,dtype=np.int16)).tobytes(),\'en\'); '
             'print(\'MMS_SUB_OK\', flush=True)')
    try:
        p = subprocess.run([sys.executable, '-c', probe], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        print('MMS_WARM_FAILED: timeout 600s', flush=True)
        return 2
    if p.returncode != 0 or 'MMS_SUB_OK' not in p.stdout:
        err = (p.stderr or '')[-300:].replace('\n', ' | ')
        print(f'MMS_WARM_FAILED: rc={p.returncode} {err}', flush=True)
        return 2
    print(f'mms fr+en warm in {time.monotonic() - t1:.1f}s', flush=True)
    print(f'WARM_OK total={time.monotonic() - t0:.1f}s', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
