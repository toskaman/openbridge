"""Dry run (no install): real discovery + real local Meta on one transcript -> printed outcome."""
import argparse
import json
import sys


def main():
    text = ' '.join(sys.argv[1:]) or 'mets les boutons de volume de la télé sur la montre'
    from src.server import create_server
    from src.adapters.android import default_remember_path
    from src.cli import ensure_discovery, default_providers
    from src.fabric.relay_store import default_owner_store
    from src.runtime import voice_layout
    server = create_server(port=0, relay_store=default_owner_store(), adb_remember=default_remember_path())
    ensure_discovery(server, default_providers(argparse.Namespace()))
    r = voice_layout.meta_propose(server, text, evidence_dir=r'E:\OpenBridge-Overnight\device-frontier\meta-runs')
    print(json.dumps({k: r.get(k) for k in ('outcome', 'detail', 'elapsed_s', 'target_label', 'target_key', 'model_run')},
                     indent=1, ensure_ascii=False))
    print(json.dumps((r.get('patch') or {}).get('widgets'), indent=1, ensure_ascii=False))
    print('devices offered:', [(d['label'], d['category']) for d in r['devices']])
    server.server_close()


if __name__ == '__main__':
    main()
