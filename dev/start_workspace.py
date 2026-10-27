"""Start Device Fabric and source-bound Forge without changing the runtime server."""
import argparse
import os
from pathlib import Path
import threading

from src.server import create_server
from src.runtime.api_v2 import reader
from src.forge.workspace import WorkspaceManager, create_workspace_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-meta', action='store_true', help='Enable the pinned main-app local Glimmer broker; no cloud fallback')
    parser.add_argument('--agent', action='store_true', help='Enable existing consent-gated agent; requires --local-meta')
    parser.add_argument('--glimmer-cpu-v2', action='store_true', help='Configure Forge proposals on the existing isolated CPU Meta service; no automatic inference')
    args = parser.parse_args()
    if args.agent and not args.local_meta:
        parser.error('--agent requires --local-meta')
    broker = planner = None
    if args.local_meta:
        from src.ai.glimmer import GlimmerBroker
        broker = GlimmerBroker()
    if args.glimmer_cpu_v2:
        from src.forge.local_models import IsolatedGlimmerCPU
        from src.forge.planner_v2 import SchemaConstrainedPlanner
        planner = SchemaConstrainedPlanner(IsolatedGlimmerCPU())
    from src.core.transactions import TransactionEngine
    from src.adapters.simulated_setting import SimulatedSetting
    private = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge'
    private.mkdir(parents=True, exist_ok=True)
    engine = TransactionEngine(private / 'simulated-transactions.sqlite', SimulatedSetting(private / 'simulated-setting.sqlite'))
    with create_server(18765, model_broker=broker, demo_engine=engine,
                       agent_dir=private/'agent' if args.agent else None) as runtime:
        manager = WorkspaceManager(reader(runtime), planner)
        try:
            workspace = create_workspace_server(18767, manager)
        except Exception:
            manager.close()
            raise
        with workspace:
            worker = threading.Thread(target=workspace.serve_forever, daemon=True)
            worker.start()
            print('Device workspace: http://127.0.0.1:18765', flush=True)
            print('Trusted Forge selector: http://127.0.0.1:18767 — no automatic discovery or model request', flush=True)
            try:
                runtime.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                workspace.shutdown()
                worker.join(timeout=2)


if __name__ == '__main__':
    main()
