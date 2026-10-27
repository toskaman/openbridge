"""Combine committed runtime with Forge in a disposable build; never modifies either checkout."""
import io,json,os,shutil,subprocess,sys,tempfile,zipfile
from datetime import datetime,timedelta
from pathlib import Path
forge=Path(__file__).resolve().parents[1];runtime=forge.parent/'OpenBridge-runtime-v2'
output=forge/'artifacts/integration'/('cross-branch-'+datetime.now().strftime('%Y-%m-%d_%H-%M-%S')+'.json')
output.parent.mkdir(parents=True,exist_ok=True)
if output.exists():raise SystemExit('Receipt exists; preserve prior evidence')
revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=runtime,text=True).strip()
with tempfile.TemporaryDirectory(prefix='openbridge-contract-integration-') as directory:
 build=Path(directory)
 assert build.resolve().parent==Path(tempfile.gettempdir()).resolve() and build.name.startswith('openbridge-contract-integration-')
 with zipfile.ZipFile(io.BytesIO(subprocess.check_output(['git','archive','--format=zip','HEAD'],cwd=runtime))) as archive:archive.extractall(build)
 overlays=['tests/integration/test_http.py','tests/fabric/test_guidance.py','config/runtime_models.json']
 if os.name!='nt':raise SystemExit('This helper requires the owner Windows delta-backup location')
 backup_root=Path(r'D:\DevBackups\OpenBridge');backup_root.mkdir(parents=True,exist_ok=True)
 backup=backup_root/('OpenBridge_'+datetime.now().strftime('%Y-%m-%d_%H-%M-%S')+'.zip')
 with zipfile.ZipFile(backup,'x',compression=zipfile.ZIP_DEFLATED) as delta:
  for relative in overlays:delta.write(build/relative,relative)
 for old in backup_root.glob('OpenBridge_*.zip'):
  if old.is_file() and datetime.fromtimestamp(old.stat().st_mtime)<datetime.now()-timedelta(days=90):old.unlink()
 print('Delta backup:',backup,'files:',overlays,flush=True)
 for relative in overlays:shutil.copy2(forge/relative,build/relative)
 shutil.copytree(forge/'src/forge',build/'src/forge',ignore=shutil.ignore_patterns('__pycache__'))
 shutil.copytree(forge/'tests/forge',build/'tests/forge',ignore=shutil.ignore_patterns('__pycache__'))
 shutil.copy2(forge/'dev/forge_runtime_integration.py',build/'dev/forge_runtime_integration.py')
 for name in ('forge_smoke','forge_runtime_smoke','forge_expiry_smoke','forge_injected_sim_smoke','forge_model_memory_smoke','forge_revocation_during_plan_smoke'):
  shutil.copy2(forge/f'tests/e2e/{name}.py',build/f'tests/e2e/{name}.py')
 guard=build/'_controlled_guard';guard.mkdir();shutil.copy2(forge/'dev/controlled_io_guard.py',guard/'sitecustomize.py')
 guard_log=build/'guard-attempts.jsonl'
 env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONPATH':str(guard)+os.pathsep+str(build),'OPENBRIDGE_TEST_GUARD_LOG':str(guard_log)}
 commands=[['-m','unittest','discover','-s','tests','-q'],['-m','dev.forge_runtime_integration'],['-m','tests.e2e.forge_smoke'],['-m','tests.e2e.forge_runtime_smoke'],['-m','tests.e2e.forge_expiry_smoke'],['-m','tests.e2e.forge_injected_sim_smoke'],['-m','tests.e2e.forge_model_memory_smoke'],['-m','tests.e2e.forge_revocation_during_plan_smoke']]
 preflight_code="import sys,socket,subprocess;g=sys.modules.get('sitecustomize');assert g is not None and g.GUARD_READY;assert socket.getaddrinfo is g.getaddrinfo and subprocess.Popen is g.GuardedPopen\ndef blocked(f):\n try:f()\n except AssertionError:return\n raise RuntimeError('Guard failed')\nblocked(lambda:socket.getaddrinfo('never-resolve.invalid',80))\nwith socket.socket() as probe:blocked(lambda:probe.connect(('127.0.0.1',11439)))\nblocked(lambda:subprocess.Popen(['adb','devices']))\nprint('I/O guard self-test passed')"
 preflight=subprocess.run([sys.executable,'-c',preflight_code],cwd=build,env={**env,'OPENBRIDGE_TEST_GUARD_LOG':str(build/'guard-self-test.jsonl')},capture_output=True,text=True,encoding='utf-8',timeout=15)
 if preflight.returncode:print(preflight.stderr);raise SystemExit('Guard self-test failed')
 print(preflight.stdout.strip(),flush=True)
 rows=[]
 for command in commands:
  result=subprocess.run([sys.executable,*command],cwd=build,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
  rows.append({'command':'python '+' '.join(command),'exit_code':result.returncode,'output':(result.stdout+result.stderr).replace(str(build),'<integration-build>').replace(str(Path.home()),'<user>')[-6000:]});print(rows[-1],flush=True)
  if result.returncode:break
 data={'runtime_revision':revision,'forge_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=forge,text=True).strip(),'build':'disposable integration copy; source checkouts unchanged','overlays':overlays+['src/forge/*','tests/forge/*'],'model_calls':0,'hardware_calls':0,'checks':rows,'guard_self_test':'passed','guard_scope':'blocks non-loopback Python DNS/sockets, model endpoint sockets, and ADB device commands; adb version is a permitted dependency check','blocked_io_attempts':guard_log.read_text(encoding='utf-8').splitlines() if guard_log.exists() else [],'passed':all(r['exit_code']==0 for r in rows) and len(rows)==len(commands) and not guard_log.exists()}
 output.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
 if not data['passed']:raise SystemExit(1)
