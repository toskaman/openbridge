"""Foreground isolated CPU-only Glimmer service using existing pinned weights. No cloud or other service changes."""
import os
from pathlib import Path
import shutil
import socket
import subprocess

with socket.socket() as check:check.bind(('127.0.0.1',11439))
executable=shutil.which('ollama')
if not executable:raise SystemExit('Ollama unavailable')
models=Path(os.environ['LOCALAPPDATA'])/'OpenBridge'/'glimmer'/'models'
if not models.is_dir():raise SystemExit('Existing Glimmer store unavailable; no download attempted')
allowed={'PATH','SYSTEMROOT','WINDIR','USERPROFILE','LOCALAPPDATA','APPDATA','TEMP','TMP','COMSPEC','PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA','PATHEXT','SYSTEMDRIVE'}
env={k:v for k,v in os.environ.items() if k.upper() in allowed}
env.update(OLLAMA_HOST='127.0.0.1:11439',OLLAMA_MODELS=str(models),OLLAMA_NO_CLOUD='1',OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1',OLLAMA_CONTEXT_LENGTH='1024',OLLAMA_KEEP_ALIVE='15s',CUDA_VISIBLE_DEVICES='-1',HIP_VISIBLE_DEVICES='-1',ROCR_VISIBLE_DEVICES='-1',OLLAMA_VULKAN='false')
print('Foreground CPU-only Meta diagnostic service: 127.0.0.1:11439; shared existing weights; other services untouched.',flush=True)
raise SystemExit(subprocess.run([executable,'serve'],env=env).returncode)
