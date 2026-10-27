"""Explicit --hardware journey through trusted source selection and deterministic rules.

Requires an already authorized, connected TV and installed Companion with permissions.
No model, install, permission grant, network reconnect, screenshot, video or device input.
--open-companion may foreground only the existing Companion activity. Receipts contain
only bounded statuses/counts, booleans and source hashes; UI XML stays transient.
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
from xml.etree import ElementTree

from dev.forge_tv_glimmer_journey import JourneyBlocked, require, ensure_companion_foreground


def companion_unpaired(xml):
    """True/False only for one exact Companion pairing row; otherwise unknown (None)."""
    try:
        root = ElementTree.fromstring(xml)
    except (ElementTree.ParseError, TypeError):
        return None
    matches = []
    for parent in root.iter():
        children = list(parent)
        labels = [n for n in children if n.get('text') == 'Paired with a PC'
                  and n.get('package') == 'fr.openbridge.companion']
        if not labels:
            continue
        values = [n.get('text') for n in children if n.get('package') == 'fr.openbridge.companion'
                  and n.get('text') in ('Yes', 'Not yet')]
        matches.append(values[0] == 'Not yet' if len(labels) == len(values) == 1 else None)
    return matches[0] if len(matches) == 1 else None


def permission_snapshot(raw):
    return {name: sorted({v == 'true' for v in re.findall(
        r'android\.permission\.' + name + r':\s*granted=(true|false)', raw)})
        for name in ('ACCESS_FINE_LOCATION', 'BLUETOOTH_SCAN', 'BLUETOOTH_CONNECT')}


def forward_created_by_journey(raw, serial):
    mappings = [row.split() for row in raw.splitlines() if row.split()[1:2] == ['tcp:47800']]
    require(not mappings or all(row == [serial, 'tcp:47800', 'tcp:47800'] for row in mappings),
            'COMPANION_FORWARD_ALREADY_OWNED_ELSEWHERE')
    return not mappings


def remove_owned_forward(android, serial, created):
    if not created:
        return True
    rows = [row.split() for row in android._run(['forward', '--list']).splitlines()
            if row.split()[1:2] == ['tcp:47800']]
    if not rows:
        return True
    if rows != [[serial, 'tcp:47800', 'tcp:47800']]:
        return False
    android._run(['-s', serial, 'forward', '--remove', 'tcp:47800'])
    return True


def read_companion_xml(android, serial):
    """Read accessibility XML without input; delete only this journey's temporary file."""
    path = '/sdcard/ob_workspace_' + secrets.token_hex(12) + '.xml'
    try:
        android._run(['-s', serial, 'shell', 'uiautomator', 'dump', path])
        return android._run(['-s', serial, 'shell', 'cat', path])
    finally:
        android._run(['-s', serial, 'shell', 'rm', path])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hardware', action='store_true')
    parser.add_argument('--open-companion', action='store_true')
    args = parser.parse_args()
    if not args.hardware:
        parser.error('Explicit --hardware is required')
    from playwright.sync_api import sync_playwright, expect
    from src.server import create_server
    from src.runtime import api_v2
    from src.forge.workspace import WorkspaceManager, create_workspace_server

    output = Path('artifacts/forge-workspace-physical')
    output.mkdir(parents=True, exist_ok=True)
    receipt = output / ('attempt-' + datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '-' + secrets.token_hex(4) + '.json')
    report = {'evidence_kind': 'PHYSICAL_TRUSTED_WORKSPACE_JOURNEY_ATTEMPT', 'status': 'NOT_VERIFIED',
              'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'model_calls': 0, 'app_installs': 0, 'permission_grants': 0, 'screenshots': 0,
              'videos': 0, 'network_reconnects': 0, 'stages': [], 'http': {}, 'cleanup': {},
              'remote_companion_unpairing': None}
    runtime = coordinator = manager = executor = None
    runtime_worker = coordinator_worker = None
    serial = tv = rid = None
    forward_created = False
    permission_before = None
    revoked = False

    def stage(code):
        report['stages'].append(code)
        print(json.dumps({'stage': code}), flush=True)

    def permissions():
        return permission_snapshot(runtime.android._run(
            ['-s', serial, 'shell', 'dumpsys', 'package', 'fr.openbridge.companion']))

    def revoke():
        nonlocal revoked
        value = executor.execute('relay_revoke', tv, {'relay_id': rid}, consent=True)
        require(value['state'] == 'VERIFIED', 'RELAY_REVOCATION_NOT_VERIFIED')
        revoked = rid not in runtime.relays.relays
        report['cleanup']['local_relay_key_removed'] = revoked
        return revoked

    def observe_unpairing():
        try:
            observed = companion_unpaired(read_companion_xml(runtime.android, serial))
            report['remote_companion_unpairing'] = True if observed is True else None
            report['cleanup']['temporary_ui_xml_removed'] = True
        except Exception:
            report['remote_companion_unpairing'] = None
            report['cleanup']['temporary_ui_xml_removed'] = False

    try:
        runtime = create_server(0)
        executor = api_v2.executor(runtime)
        discovery = executor.execute('bounded_discovery', 'fabric', {'providers': ['android']})
        require(discovery['state'] == 'VERIFIED', 'ANDROID_DISCOVERY_NOT_VERIFIED')
        tvs = [key for key, device in runtime.fabric_registry.devices.items()
               if device['category'] == 'tv' and any(identity.strong for identity in device['identifiers'])]
        require(len(tvs) == 1, 'ONE_ALREADY_CONNECTED_AUTHORIZED_TV_REQUIRED')
        tv = tvs[0]
        handle = next(iter(runtime.fabric_registry.devices[tv]['handles'].values()))
        serial = next(key for key, value in runtime.android._handles.items() if value == handle)
        ensure_companion_foreground(runtime.android, serial, args.open_companion, report)
        disabled = runtime.android._run(['-s', serial, 'shell', 'pm', 'list', 'packages', '-d'])
        require('com.android.bluetooth' not in disabled, 'TV_BLUETOOTH_PACKAGE_DISABLED')
        permission_before = permissions()
        forward_created = forward_created_by_journey(runtime.android._run(['forward', '--list']), serial)
        stage('existing_authorized_tv_ready')

        pair = runtime.relay_action('/api/relay-pair-start', {'device_id': handle})
        rid = pair['relay_id']
        time.sleep(2)
        xml = read_companion_xml(runtime.android, serial)
        report['cleanup']['temporary_ui_xml_removed'] = True
        code = re.search(r'Pairing code (\d{6})', xml)
        require(code is not None, 'PAIRING_CODE_NOT_AVAILABLE_ON_DEVICE')
        paired = runtime.relay_action('/api/relay-pair-confirm', {'device_id': handle, 'code': code.group(1)})
        del xml, code
        require(paired['state'] == 'PAIRED' and paired['eligible_for_ble'] is True,
                'EXISTING_RELAY_PERMISSIONS_NOT_READY')
        scan = executor.execute('relay_ble_scan', tv, {'relay_id': rid, 'seconds': 10}, consent=True)
        require(scan['state'] == 'VERIFIED' and scan['verified'] is True, 'PHYSICAL_SCAN_NOT_VERIFIED')
        stage('paired_and_ten_second_scan_verified')

        manager = WorkspaceManager(api_v2.reader(runtime))
        coordinator = create_workspace_server(0, manager, main_port=runtime.server_port)
        runtime_worker = threading.Thread(target=runtime.serve_forever, daemon=True)
        coordinator_worker = threading.Thread(target=coordinator.serve_forever, daemon=True)
        runtime_worker.start()
        coordinator_worker.start()
        base = 'http://127.0.0.1:' + str(coordinator.server_port)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(type(error).__name__))
                page.goto(base, wait_until='networkidle')
                with page.expect_response(lambda r: r.url == base + '/api/candidates') as candidates_response:
                    page.locator('#refresh-routes').click()
                response = candidates_response.value
                require(response.status == 200, 'TRUSTED_CANDIDATES_UNAVAILABLE')
                rows = response.json()['candidates']
                require(bool(rows) and all(row['simulation'] is False for row in rows), 'REAL_CANDIDATE_REQUIRED')
                report['physical_candidates'] = len(rows)
                expect(page.locator('#routes .eyebrow').first).to_have_text('PHYSICAL / READ-ONLY')
                with page.expect_response(lambda r: r.url == base + '/api/select') as selection:
                    page.get_by_role('button', name='Create bound workspace').first.click()
                require(selection.value.status == 200, 'BOUND_WORKSPACE_SELECTION_FAILED')
                selected = selection.value.json()
                session_id = selected['id']
                child = manager._sessions[session_id]['server']
                child_base = 'http://127.0.0.1:' + str(child.server_port)
                page.get_by_role('link', name='Open read-only bound workspace').click()
                expect(page.locator('#source-pill')).to_contain_text('PHYSICAL')
                page.select_option('#planner', 'rules')
                with page.expect_response(lambda r: r.url == child_base + '/api/plan') as planned:
                    page.locator('#plan').click()
                require(planned.value.status == 200, 'RULES_PLAN_NOT_ACCEPTED')
                proposal = planned.value.json()
                require(proposal['source'] == 'RULES' and proposal['plan']['decision'] == 'propose', 'RULES_PLAN_INVALID')
                expect(page.locator('#plan-result')).to_contain_text('Path proposed')
                page.locator('#consent').check()
                with page.expect_response(lambda r: r.url == child_base + '/api/publish') as published:
                    page.locator('#publish').click()
                require(published.value.status == 200, 'PUBLICATION_NOT_VERIFIED')
                value = published.value.json()
                require(value['simulation'] is False and value['verification']['read']['simulation'] is False,
                        'PHYSICAL_PUBLICATION_MISLABELED')
                report['http']['publish'] = 200
                expect(page.locator('#operation')).to_contain_text('First observation read verified')
                with page.expect_response(lambda r: r.url == child_base + child.observation_path) as observed:
                    page.locator('#test').click()
                require(observed.value.status == 200 and observed.value.json()['simulation'] is False, 'PHYSICAL_READ_FAILED')
                report['http']['read'] = 200
                with page.expect_response(lambda r: r.url == child_base + '/api/documents') as documents:
                    page.locator('#documents').click()
                require(documents.value.status == 200 and documents.value.json()['openapi']['openapi'] == '3.1.0', 'DOCUMENT_EXPORT_FAILED')
                report['http']['documents'] = 200
                stage('trusted_selection_rules_consent_publication_read_documents_verified')
                require(revoke(), 'LOCAL_RELAY_KEY_NOT_REMOVED')
                time.sleep(1)
                observe_unpairing()
                response = page.request.get(child_base + child.observation_path,
                                            headers={'Authorization': 'Bearer ' + child.token})
                require(response.status == 409, 'REVOKED_READ_NOT_DENIED')
                report['http']['after_relay_revocation'] = response.status
                with page.expect_response(lambda r: r.url == child_base + '/api/remove') as removed:
                    page.locator('#remove').click()
                require(removed.value.status == 200, 'SERVICE_REMOVAL_NOT_CONFIRMED')
                report['http']['remove'] = 200
                response = page.request.get(child_base + child.observation_path,
                                            headers={'Authorization': 'Bearer ' + child.token})
                require(response.status == 404, 'REMOVED_SERVICE_STILL_ACCESSIBLE')
                report['http']['after_removal'] = response.status
                page.goto(base, wait_until='networkidle')
                with page.expect_response(lambda r: r.url == base + '/api/close') as closed:
                    page.get_by_role('button', name='Close workspace and remove services').click()
                require(closed.value.status == 200 and not manager.sessions(), 'WORKSPACE_CLOSURE_NOT_CONFIRMED')
                report['http']['close_workspace'] = 200
                require(not errors, 'BROWSER_SCRIPT_ERRORS')
                report['status'] = 'REAL_HARDWARE_VERIFIED'
                stage('revocation_read_denial_service_and_workspace_removal_verified')
            finally:
                browser.close()
    except Exception as error:
        report['failure'] = str(error) if isinstance(error, JourneyBlocked) else type(error).__name__
        stage('journey_not_verified')
    finally:
        if runtime is not None:
            if rid is not None and rid in runtime.relays.relays:
                try:
                    revoke()
                    observe_unpairing()
                except Exception:
                    report['cleanup']['local_relay_key_removed'] = False
            if serial is not None:
                try:
                    report['cleanup']['temporary_forward_removed'] = remove_owned_forward(runtime.android, serial, forward_created)
                except Exception:
                    report['cleanup']['temporary_forward_removed'] = False
            if permission_before is not None:
                try:
                    report['android_permissions_unchanged'] = permissions() == permission_before
                except Exception:
                    report['android_permissions_unchanged'] = False
        if coordinator is not None:
            try:
                if coordinator_worker is not None and coordinator_worker.is_alive(): coordinator.shutdown()
                coordinator.server_close()
                if coordinator_worker is not None: coordinator_worker.join(timeout=3)
                report['cleanup']['coordinator_and_bound_workspaces_closed'] = True
            except Exception:
                report['cleanup']['coordinator_and_bound_workspaces_closed'] = False
        elif manager is not None:
            try:
                manager.close()
                report['cleanup']['coordinator_and_bound_workspaces_closed'] = True
            except Exception:
                report['cleanup']['coordinator_and_bound_workspaces_closed'] = False
        if runtime is not None:
            try:
                if runtime_worker is not None and runtime_worker.is_alive(): runtime.shutdown()
                runtime.server_close()
                if runtime_worker is not None: runtime_worker.join(timeout=3)
                report['cleanup']['runtime_closed'] = True
            except Exception:
                report['cleanup']['runtime_closed'] = False
        if report['status'] == 'REAL_HARDWARE_VERIFIED' and (
                report.get('android_permissions_unchanged') is not True
                or any(value is not True for value in report['cleanup'].values())):
            report['status'] = 'VERIFIED_WITH_CLEANUP_PENDING'
        report['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
        with receipt.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
        print(json.dumps({'status': report['status'], 'receipt': str(receipt), 'failure': report.get('failure')}), flush=True)
    return 0 if report['status'] == 'REAL_HARDWARE_VERIFIED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
