"""Explicit owner-authorized TV/Meta verification; requires an already-ready Companion.

No installation, permission grants, package changes, screenshots or video.
Optional --open-companion brings only the installed Companion activity forward.
Uses product pairing/scan/revocation APIs, one local Meta plan and the actual Forge UI.
Run only with --hardware. Receipts omit device addresses, pairing secrets and tokens.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
from urllib.request import Request, build_opener, ProxyHandler


class JourneyBlocked(ValueError):
    pass


def require(condition, code):
    if not condition: raise JourneyBlocked(code)


def verify_revoked_read(page,forge):
    """Verify server denial even when the UI correctly disables its Test button."""
    response=page.request.get('http://127.0.0.1:'+str(forge.server_port)+forge.observation_path,
                              headers={'Authorization':'Bearer '+forge.token})
    require(response.status==409,'REVOKED_SOURCE_READ_NOT_DENIED')
    return response.status


def ensure_companion_foreground(android,serial,allow_open,report):
    """Fail closed on readiness; a timed-out launch has an unknown outcome."""
    report.setdefault('activity_launch_attempts',0);report.setdefault('activity_launches',0)
    pattern=r'(?:mResumedActivity|topResumedActivity).*fr\.openbridge\.companion'
    activity=android._run(['-s',serial,'shell','dumpsys','activity','activities'])
    if allow_open and re.search(pattern,activity) is None:
        report['activity_launch_attempts']=1;report['activity_launches']=None
        android._run(['-s',serial,'shell','am','start','-W','-n','fr.openbridge.companion/.MainActivity'])
        report['activity_launches']=1
        activity=android._run(['-s',serial,'shell','dumpsys','activity','activities'])
    require(re.search(pattern,activity) is not None,'COMPANION_MUST_ALREADY_BE_FOREGROUND')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hardware',action='store_true',help='Use the owner-authorized connected TV; no automatic setup')
    parser.add_argument('--open-companion',action='store_true',help='Bring the installed Companion forward if needed; no install/grant')
    args=parser.parse_args()
    if not args.hardware:parser.error('Explicit --hardware is required')
    from playwright.sync_api import sync_playwright,expect
    from src.server import create_server
    from src.runtime import api_v2
    from src.forge.demo_host import create_forge_server
    from src.forge.runtime_bridge import RuntimeV1Provider
    from src.forge.local_models import IsolatedGlimmerCPU
    from src.forge.planner_v2 import SchemaConstrainedPlanner

    output=Path('artifacts/forge-physical-tv');output.mkdir(parents=True,exist_ok=True)
    receipt_path=output/('attempt-'+datetime.now().strftime('%Y-%m-%d_%H-%M-%S')+'-'+secrets.token_hex(4)+'.json')
    report={'evidence_kind':'PHYSICAL_TV_LOCAL_META_JOURNEY_ATTEMPT','status':'NOT_VERIFIED',
            'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
            'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'model_provider_cost_usd':0.0,'model_calls':0,'app_installs':0,'permission_grants':0,
            'device_setting_changes_outside_pairing':0,'activity_launches':0,'screenshots':0,'videos':0,'stages':[],'cleanup':{}}
    runtime=forge=worker=executor=rid=serial=None
    broker=IsolatedGlimmerCPU();planner=SchemaConstrainedPlanner(broker)
    loaded_before=True;prepare_attempted=False;forward_created=False;xml_path=None;permission_before=None
    def stage(value):
        report['stages'].append(value);print(json.dumps({'stage':value}),flush=True)
    def permissions():
        raw=runtime.android._run(['-s',serial,'shell','dumpsys','package','fr.openbridge.companion'])
        values={}
        for name in ('ACCESS_FINE_LOCATION','BLUETOOTH_SCAN','BLUETOOTH_CONNECT'):
            matches=re.findall(r'android\.permission\.'+name+r':\s*granted=(true|false)',raw)
            values[name]=sorted(set(matches))
        return values
    try:
        runtime=create_server(0);executor=api_v2.executor(runtime)
        discovery=executor.execute('bounded_discovery','fabric',{'providers':['android']})
        require(discovery['state']=='VERIFIED','ANDROID_DISCOVERY_NOT_VERIFIED')
        tvs=[k for k,d in runtime.fabric_registry.devices.items() if d['category']=='tv' and any(i.strong for i in d['identifiers'])]
        require(len(tvs)==1,'ONE_AUTHORIZED_TV_REQUIRED')
        tv=tvs[0];handle=next(iter(runtime.fabric_registry.devices[tv]['handles'].values()))
        serial=next(s for s,h in runtime.android._handles.items() if h==handle)
        ensure_companion_foreground(runtime.android,serial,args.open_companion,report)
        disabled=runtime.android._run(['-s',serial,'shell','pm','list','packages','-d'])
        require('com.android.bluetooth' not in disabled,'TV_BLUETOOTH_PACKAGE_DISABLED')
        permission_before=permissions()
        forwards=runtime.android._run(['forward','--list']).splitlines()
        mappings=[row.split() for row in forwards if 'tcp:47800' in row.split()[1:2]]
        require(not mappings or all(row==[serial,'tcp:47800','tcp:47800'] for row in mappings),'COMPANION_FORWARD_ALREADY_OWNED_ELSEWHERE')
        forward_created=not mappings
        stage('ready_tv_found_no_setup_changes')
        opener=build_opener(ProxyHandler({}))
        with opener.open(broker.endpoint+'/api/ps',timeout=5) as response:
            resident=json.load(response)['models']
        loaded_before=any(m.get('name',m.get('model'))==broker.model_id for m in resident)
        report['model_initially_loaded']=loaded_before
        stage('preparing_local_meta_without_device_data')
        prepare_attempted=True
        report['model_prepare']=planner.prepare()

        pair=runtime.relay_action('/api/relay-pair-start',{'device_id':handle});rid=pair['relay_id']
        time.sleep(2)
        xml_path='/sdcard/ob_forge_'+secrets.token_hex(8)+'.xml'
        runtime.android._run(['-s',serial,'shell','uiautomator','dump',xml_path])
        xml=runtime.android._run(['-s',serial,'shell','cat',xml_path])
        code=re.search(r'Pairing code (\d{6})',xml)
        require(code is not None,'PAIRING_CODE_NOT_AVAILABLE_ON_DEVICE')
        paired=runtime.relay_action('/api/relay-pair-confirm',{'device_id':handle,'code':code.group(1)})
        runtime.android._run(['-s',serial,'shell','rm',xml_path]);xml_path=None
        require(paired['state']=='PAIRED' and paired['eligible_for_ble'] is True,'EXISTING_RELAY_PERMISSIONS_NOT_READY')
        report['pairing_session_created']=True
        stage('paired_through_product_api_with_existing_permissions')
        scan=executor.execute('relay_ble_scan',tv,{'relay_id':rid,'seconds':10},consent=True)
        require(scan['state']=='VERIFIED' and scan['verified'] is True,'PHYSICAL_SCAN_NOT_VERIFIED')
        read=api_v2.reader(runtime)
        targets=sorted({l['child'] for l in read('/api/v2/graph')['links'] if l['source']=='RELAY:'+rid})
        require(bool(targets),'NO_RELAY_OBSERVATION_AVAILABLE')
        # Any one real advertiser suffices; target identity remains local and immutable.
        provider=RuntimeV1Provider(read,tv+':ble_relay',targets[0],rid)
        forge=create_forge_server(0,planner,provider=provider,capability_id=provider.capability_id)
        worker=threading.Thread(target=forge.serve_forever,daemon=True);worker.start()
        base='http://127.0.0.1:'+str(forge.server_port)
        report['physical_advertisers']=len(targets)
        stage('physical_source_bound_starting_browser_meta_proposal')
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
                page.on('pageerror',lambda error:errors.append(type(error).__name__))
                page.goto(base,wait_until='networkidle')
                expect(page.locator('#source-pill')).to_contain_text('PHYSICAL')
                report['model_calls']=None  # Request outcome is ambiguous until its response is validated.
                with page.expect_response(lambda r:r.url==base+'/api/plan' and r.request.method=='POST',timeout=240000) as planned:
                    page.locator('#plan').click()
                plan_response=planned.value;plan=plan_response.json()
                if plan_response.status!=200:
                    report['planner_error']=plan.get('error','UNKNOWN_PLANNER_ERROR')
                    report['model_calls']=None
                require(plan_response.status==200,'LOCAL_META_PROPOSAL_NOT_ACCEPTED')
                require(plan['source']=='LOCAL_META' and plan['model_id']==broker.model_id and plan['plan']['decision']=='propose','LOCAL_META_PROPOSAL_IDENTITY_INVALID')
                report['model_calls']=1
                report['model']={k:plan[k] for k in ('model_id','model_digest','elapsed_ms','usage','provider_cost_usd')}
                stage('local_meta_proposal_validated')
                expect(page.locator('#plan-result')).to_contain_text('Path proposed')
                page.locator('#consent').check()
                with page.expect_response(lambda r:r.url==base+'/api/publish') as published:page.locator('#publish').click()
                require(published.value.status==200,'PUBLICATION_NOT_VERIFIED')
                report['http']={'publish':published.value.status}
                publication=published.value.json()
                require(publication['simulation'] is False and publication['verification']['read']['simulation'] is False,'PHYSICAL_PUBLICATION_MISLABELED')
                expect(page.locator('#operation')).to_contain_text('First observation read verified')
                with page.expect_response(lambda r:r.url==base+forge.observation_path) as observed:page.locator('#test').click()
                require(observed.value.status==200 and observed.value.json()['simulation'] is False,'AUTHENTICATED_PHYSICAL_READ_FAILED')
                report['http']['read']=observed.value.status
                with page.expect_response(lambda r:r.url==base+'/api/documents') as documents:page.locator('#documents').click()
                require(documents.value.status==200 and documents.value.json()['openapi']['openapi']=='3.1.0','DOCUMENT_EXPORT_FAILED')
                report['http']['documents']=documents.value.status
                stage('consent_publication_fresh_read_and_documents_verified')
                revoked=executor.execute('relay_revoke',tv,{'relay_id':rid},consent=True)
                require(revoked['state']=='VERIFIED','RELAY_REVOCATION_NOT_VERIFIED')
                report['cleanup']['local_relay_key_removed']=True
                report['remote_companion_unpairing']='Not independently verified; the runtime primitive checks local key removal only.'
                stage('verifying_authenticated_denial_after_local_revocation')
                report['http']['after_relay_revocation']=verify_revoked_read(page,forge)
                with page.expect_response(lambda r:r.url==base+'/api/remove') as removed:page.locator('#remove').click()
                require(removed.value.status==200,'SERVICE_REMOVAL_NOT_CONFIRMED')
                report['http']['remove']=removed.value.status
                response=page.request.get(base+forge.observation_path,headers={'Authorization':'Bearer '+forge.token})
                require(response.status==404,'REMOVED_SERVICE_STILL_ACCESSIBLE')
                report['http']['after_removal']=response.status
                require(not errors,'BROWSER_SCRIPT_ERRORS')
                report['http']={'publish':200,'read':200,'documents':200,'after_relay_revocation':409,'remove':200,'after_removal':404}
                report['consent_source']='Owner-authorized headless UI driver; not a new human Android permission-dialog acceptance.'
                report['status']='REAL_HARDWARE_VERIFIED'
                stage('revocation_denial_and_service_removal_verified')
            finally:browser.close()
    except Exception as error:
        report['failure']=str(error) if isinstance(error,JourneyBlocked) else type(error).__name__
        report['failure_detail_sha256']=hashlib.sha256(str(error).encode()).hexdigest()
        stage('journey_not_verified')
    finally:
        if runtime is not None:
            if rid is not None and rid in runtime.relays.relays:
                try:
                    executor.execute('relay_revoke',tv,{'relay_id':rid},consent=True)
                    report['cleanup']['local_relay_key_removed']=rid not in runtime.relays.relays
                    report['remote_companion_unpairing']='Not independently verified; remote revoke is best effort.'
                except Exception:report['cleanup']['local_relay_key_removed']=False
            if xml_path is not None:
                try:runtime.android._run(['-s',serial,'shell','rm',xml_path]);report['cleanup']['temporary_ui_xml_removed']=True
                except Exception:report['cleanup']['temporary_ui_xml_removed']=False
            if forward_created and serial is not None:
                try:
                    lines=runtime.android._run(['forward','--list']).splitlines()
                    if any(row.split()==[serial,'tcp:47800','tcp:47800'] for row in lines):runtime.android._run(['-s',serial,'forward','--remove','tcp:47800'])
                    report['cleanup']['temporary_forward_removed']=True
                except Exception:report['cleanup']['temporary_forward_removed']=False
            if permission_before is not None:
                try:report['android_permissions_unchanged']=permissions()==permission_before
                except Exception:report['android_permissions_unchanged']=False
        if forge is not None:
            forge.shutdown();forge.server_close()
            if worker is not None:worker.join(timeout=5)
            report['cleanup']['forge_closed']=True
        if runtime is not None:runtime.server_close()
        if prepare_attempted and not loaded_before:
            try:report['model_release']=planner.release()
            except Exception:report['cleanup']['model_release_confirmed']=False
        if report['status']=='REAL_HARDWARE_VERIFIED' and (report.get('android_permissions_unchanged') is not True or any(value is not True for value in report['cleanup'].values())):
            report['status']='VERIFIED_WITH_CLEANUP_PENDING'
        report['completed_at_utc']=datetime.now(timezone.utc).isoformat()
        with receipt_path.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2);stream.write('\n')
        print(json.dumps({'status':report['status'],'receipt':str(receipt_path),'failure':report.get('failure')}),flush=True)
    return 0 if report['status']=='REAL_HARDWARE_VERIFIED' else 1


if __name__=='__main__':raise SystemExit(main())
