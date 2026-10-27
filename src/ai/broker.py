"""Pinned Meta-only, advisory broker with durable supervised credit reservations."""
from dataclasses import dataclass
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

MODEL_ID = 'muse-spark-1.3'
ENDPOINT = 'https://api.meta.ai/v1/chat/completions'
RESERVATION_MICRO_USD = 100_000
ALLOWED_FACTS = {'battery_percent', 'storage_free_gb', 'screen_timeout_seconds'}


class ModelBlocked(ValueError):
    """The request did not pass the runtime or budget boundary."""


@dataclass(frozen=True)
class CreditPermit:
    observation_id: str
    verified_at: datetime
    free_balance_usd: float
    session_budget_usd: float


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class MetaTransport:
    def __init__(self, api_key):
        self._api_key = api_key

    def __call__(self, payload):
        if not self._api_key:
            raise ModelBlocked('Meta credential unavailable')
        request = Request(ENDPOINT, data=json.dumps(payload).encode(), method='POST',
                          headers={'Authorization': 'Bearer '+self._api_key, 'Content-Type': 'application/json'})
        # Do not forward the credential through redirects or environment proxies.
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=45) as response:
            data = response.read(131073)
            if len(data) > 131072:
                raise ModelBlocked('Provider response too large')
            return json.loads(data)


class RuntimeModelBroker:
    def __init__(self, budget_path, permit=None, transport=None):
        self.budget_path = Path(budget_path)
        self.permit = permit
        self.transport = transport

    def _reserve(self):
        permit = self.permit
        if permit is None or permit.verified_at.tzinfo is None:
            raise ModelBlocked('Fresh promotional-credit verification required')
        age = (datetime.now(timezone.utc)-permit.verified_at).total_seconds()
        if not 0 <= age <= 300:
            raise ModelBlocked('Promotional-credit observation expired or invalid')
        values = (permit.free_balance_usd, permit.session_budget_usd)
        if any(isinstance(v, bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
            raise ModelBlocked('Invalid credit values')
        if not 0 < permit.session_budget_usd <= 0.20 or not permit.observation_id or len(permit.observation_id)>120:
            raise ModelBlocked('Invalid supervised session allowance')
        ceiling = min(int(permit.session_budget_usd*1_000_000), int((permit.free_balance_usd-1)*1_000_000))
        if ceiling < RESERVATION_MICRO_USD:
            raise ModelBlocked('Insufficient verified free-credit headroom')
        self.budget_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.budget_path, timeout=5)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS reservations (id INTEGER PRIMARY KEY, observation TEXT, reserved INTEGER, recorded REAL)')
            db.execute('BEGIN IMMEDIATE')
            used = db.execute('SELECT COALESCE(SUM(reserved),0) FROM reservations WHERE observation=?',(permit.observation_id,)).fetchone()[0]
            total = db.execute('SELECT COALESCE(SUM(reserved),0) FROM reservations').fetchone()[0]
            if used+RESERVATION_MICRO_USD > ceiling or total+RESERVATION_MICRO_USD > 1_000_000:
                raise ModelBlocked('Conservative local credit budget exhausted')
            db.execute('INSERT INTO reservations(observation,reserved,recorded) VALUES(?,?,?)',
                       (permit.observation_id,RESERVATION_MICRO_USD,time.time()))

    def recommend(self, facts):
        if not isinstance(facts,dict) or not facts or set(facts)-ALLOWED_FACTS:
            raise ModelBlocked('Only approved synthetic fixture facts may be sent')
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 or v>1_000_000 for v in facts.values()):
            raise ModelBlocked('Invalid fixture facts')
        if self.transport is None:
            raise ModelBlocked('Meta transport unavailable')
        payload = {'model':MODEL_ID,'max_completion_tokens':4000,  # muse-spark-1.3 is a reasoning model: leave room for reasoning AND the JSON answer
                   'messages':[{'role':'developer','content':
                       'Return ONLY a JSON object with summary (string), evidence_refs (nonempty array of keys from the supplied facts), action (exactly inspect_only), uncertainty (string). '
                       'These are SIMULATED facts, not a physical device. Explain one useful read-only observation. No commands, writes, claimed optimization or rollback.'},
                       {'role':'user','content':json.dumps({'source':'SIMULATED','facts':facts},sort_keys=True)}]}
        self._reserve()  # Committed before network I/O; failures are never refunded.
        started = time.monotonic()
        try:
            response = self.transport(payload)
            if response.get('model') != MODEL_ID:
                raise ModelBlocked('Returned model identity is not approved')
            usage = response['usage']
            for field in ('prompt_tokens','completion_tokens'):
                if type(usage[field]) is not int or not 0 <= usage[field] <= 100_000:
                    raise ModelBlocked('Invalid provider usage')
            content = response['choices'][0]['message'].get('content')
            if not isinstance(content, str) or not content.strip():
                raise ModelBlocked('Model returned no content (reasoning budget exhausted); raise max_completion_tokens')
            proposal = json.loads(content)
            if not isinstance(proposal,dict) or set(proposal) != {'summary','evidence_refs','action','uncertainty'}:
                raise ModelBlocked('Invalid advisory schema')
            if proposal['action'] != 'inspect_only' or any(not isinstance(proposal[k],str) or not 1 <= len(proposal[k]) <= 2000 for k in ('summary','uncertainty')):
                raise ModelBlocked('Unsafe or malformed advisory')
            refs=proposal['evidence_refs']
            if not isinstance(refs,list) or not refs or len(refs)>len(facts) or any(not isinstance(ref,str) or ref not in facts for ref in refs):
                raise ModelBlocked('Advisory references unknown evidence')
            estimate=(usage['prompt_tokens']*1.25+usage['completion_tokens']*4.25)/1_000_000
            if estimate>0.10:
                raise ModelBlocked('Provider usage exceeded conservative request reservation')
            return {'model_id':MODEL_ID,'provider':'Meta Model API','request_id':response.get('id'),
                    'source':'SIMULATED','proposal':proposal,'usage':usage,
                    'estimated_cost_usd':estimate,'reserved_usd':0.10,
                    'elapsed_ms':round((time.monotonic()-started)*1000),
                    'input_sha256':hashlib.sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest()}
        except ModelBlocked:
            raise
        except Exception:
            raise ModelBlocked('Meta call failed; reservation retained; no automatic retry') from None
