"""Verifiable device agent: observe -> Meta plan -> deterministic gate -> consented act -> independent verify -> exact Undo."""
import threading
import time
import uuid
from src.adapters.android_package import AndroidPackageState, ALLOWED_PACKAGES, DISABLED
from src.core.gate import evaluate, ALLOW_WITH_CONSENT
from src.core.transactions import TransactionEngine, TransactionBlocked

FACT_KEYS=('battery_percent','storage_free_gb','screen_timeout_seconds')


class AgentBlocked(ValueError):
    pass


class DeviceAgent:
    def __init__(self,broker,android,journal_dir,package_factory=AndroidPackageState,engine_factory=None):
        self.broker=broker;self.android=android;self.journal_dir=journal_dir
        self.package_factory=package_factory
        self.engine_factory=engine_factory or (lambda adapter:TransactionEngine(journal_dir/('agent-'+adapter.identity[-16:]+'.sqlite'),adapter,allow_physical=True))
        self._plans={};self._lock=threading.Lock()

    def _adapters(self,handle):
        found={}
        for package in sorted(ALLOWED_PACKAGES):
            try:
                adapter=self.package_factory(self.android,handle,package)
                found[package]=(adapter,adapter.read_setting())
            except ValueError:continue  # Not installed or unverifiable: never a candidate.
        return found

    def pending(self,handle):
        """Allowlisted packages with an unfinished journaled change (e.g. after a server restart)."""
        out=[]
        for package,(adapter,_) in self._adapters(handle).items():
            if self.engine_factory(adapter).status()['active']:out.append(package)
        return out

    def recover(self,handle):
        """Restore every unfinished change to its exact journaled original. Never starts a new change."""
        results=[]
        for package,(adapter,_) in self._adapters(handle).items():
            engine=self.engine_factory(adapter);active=engine.status()['active']
            if not active:continue
            done=engine.revert(active['id']);after=adapter.read_setting()
            exact=done['state']=='REVERTED' and after==active['before']
            if not exact:raise AgentBlocked(f'Recovery of {package} could not be verified')
            results.append({'package':package,'state':'REVERTED','restored_code':after,'exact':True})
        return results

    def plan(self,handle,goal='review'):
        if self.pending(handle):
            raise AgentBlocked('An earlier change is still journaled; recover it before planning')
        trace=[{'step':'OBSERVE','at':time.time()}]
        report=self.android.inspect(handle)
        facts={i['key']:i['value'] for i in report['evidence'] if i['key'] in FACT_KEYS}
        adapters=self._adapters(handle)
        candidates={p:('disabled' if s==DISABLED else 'enabled') for p,(_,s) in adapters.items()}
        trace.append({'step':'CANDIDATES','count':len(candidates)})
        model=self.broker.plan(facts,candidates,goal)
        trace.append({'step':'META_PLAN','model_id':model['model_id'],'request_id':model['request_id']})
        gate=evaluate(model['proposal'],{p:s for p,(_,s) in adapters.items()})
        trace.append({'step':'GATE','decision':gate['decision']})
        plan_id='plan-'+uuid.uuid4().hex
        with self._lock:
            self._plans[plan_id]={'handle':handle,'proposal':model['proposal'],'gate':gate,'state':'PLANNED',
                                  'adapter':adapters.get(model['proposal'].get('package'),(None,None))[0]}
        return {'plan_id':plan_id,'goal':goal,'source':'ADB','facts':facts,'candidates':candidates,'model':model,'gate':gate,'trace':trace}

    def _get(self,plan_id):
        with self._lock:
            plan=self._plans.get(plan_id)
        if plan is None:raise AgentBlocked('Unknown or expired plan')
        return plan

    def execute(self,plan_id,consent):
        plan=self._get(plan_id)
        if plan['gate']['decision']!=ALLOW_WITH_CONSENT:raise AgentBlocked('The deterministic gate did not allow this plan')
        if consent is not True:raise AgentBlocked('Owner consent is required')
        if plan['state']!='PLANNED':raise AgentBlocked('Plan already executed')
        engine=self.engine_factory(plan['adapter'])
        try:
            before=engine.prepare(plan_id,DISABLED,consent=True)
            applied=engine.apply(plan_id)
            observed=plan['adapter'].read_setting()
        except TransactionBlocked as error:
            restored=engine.revert(plan_id)
            plan['state']='BLOCKED'
            raise AgentBlocked(f'{error}; original state restored ({restored["state"]})') from None
        if observed!=DISABLED:raise AgentBlocked('Independent read-back failed')
        plan['state']='VERIFIED';plan['engine']=engine
        return {'plan_id':plan_id,'state':applied['state'],'package':plan['proposal']['package'],
                'before_code':before['before'],'observed_code':observed,'verified':True}

    def undo(self,plan_id):
        plan=self._get(plan_id)
        if plan.get('state')!='VERIFIED':raise AgentBlocked('Nothing verified to undo')
        engine=plan['engine'];result=engine.revert(plan_id)
        after=plan['adapter'].read_setting()
        tx=engine.get(plan_id)
        if result['state']!='REVERTED' or after!=tx['before']:raise AgentBlocked('Exact restoration not verified')
        plan['state']='REVERTED'
        return {'plan_id':plan_id,'state':'REVERTED','restored_code':after,'exact':True}
