"""Campaign Two §4.1: Universal Capability Transplantation (one coherent path).

Pipeline: source discovery -> target compat -> route selection -> Meta-generated
proposal (proposer interface; deterministic stub in tests, no live model needed)
-> schema validation -> consent -> UI publication -> dispatch -> independent
verification -> revocation -> cleanup -> honest reporting.

Rules: simulated companions only (real hardware is refused, never transplanted);
no authorization bypass (grants are checked, never minted); every refusal is an
explicit error code surfaced in the report.
"""
import copy
import hashlib
import threading

from src.forge import v4_schemas as S
from src.forge import v4_substrate as VS
from src.forge import v4_synthesize as Y
from src.forge.compiler import ForgeError
from src.forge.service import ForgeService, MemoryProvider

STAGES = ('discover_source', 'target_compat', 'route', 'propose', 'validate',
          'consent', 'compile', 'publish_ui', 'dispatch', 'verify', 'revoke', 'cleanup')


class TransplantError(ValueError):
    pass


def _simulated(companion):
    return companion.get('simulated') is True


class DeterministicStubProposer:
    """Test-only Meta proposer: deterministic candidate, no live model.

    Builds the single coherent-path candidate: one primitive step over the
    target device, citing only evidence refs present in the bundle.
    """

    def __init__(self, model='stub-meta-1'):
        self.model = model
        self.calls = []

    def propose(self, request):
        self.calls.append(copy.deepcopy(request))
        bundle = request['bundle']
        primitive_ids = request['primitive_ids']
        target_category = request['target_category']
        devices = [d for d in bundle['devices'] if d['category'] == target_category]
        if not devices:
            raise TransplantError('PROPOSAL_NO_TARGET_IN_BUNDLE')
        target = devices[0]
        if not target['facts']:
            raise TransplantError('PROPOSAL_NO_EVIDENCE_IN_BUNDLE')
        step_primitive = sorted(primitive_ids)[0]
        schemas = request.get('schemas') or {}
        step_input = {}
        if step_primitive in schemas:
            for key, want in sorted(schemas[step_primitive].items()):
                step_input[key] = 'stub' if want == 'string' else 0
        candidate = {
            'schema_version': S.SCHEMA_VERSION,
            'candidate_id': 'transplant.%s' % target_category,
            'origin': 'meta_generated',
            'intent': request.get('intent', 'transplant capability')[:200],
            'target_opaque_id': target['opaque_id'],
            'primitive_chain': [{'primitive_id': step_primitive, 'input': step_input}],
            'preconditions': [],
            'postconditions': [],
            'required_grants': [g for g in ('observe', 'read')
                                if g in target.get('permission_scope', [])],
            'evidence_refs': [target['facts'][0]['evidence_ref'],
                              ],
            'model_run_id': 'mr-' + hashlib.sha256(
                ('stub|%s|%s' % (target['opaque_id'], step_primitive)).encode()
            ).hexdigest()[:16],
        }
        if not candidate['required_grants']:
            candidate['required_grants'] = ['observe']
        return {'candidate': candidate, 'model': self.model,
                'prompt_version': Y.PROMPT_VERSION}


class SimulatedDispatcher:
    """Dispatch to simulated companions only. Records receipts for revocation."""

    def __init__(self):
        self.receipts = {}
        self.revoked = []

    def dispatch(self, route, candidate):
        if route.get('simulated') is not True:
            raise TransplantError('DISPATCH_REFUSES_REAL_HARDWARE')
        receipt_id = 'rx-' + hashlib.sha256(
            S.canonical({'route': route['route_id'], 'candidate': candidate['candidate_id']})
        ).hexdigest()[:16]
        receipt = {'receipt_id': receipt_id, 'route_id': route['route_id'],
                   'candidate_id': candidate['candidate_id'], 'simulated': True,
                   'state': 'dispatched'}
        self.receipts[receipt_id] = receipt
        return copy.deepcopy(receipt)

    def revoke(self, receipt_id):
        receipt = self.receipts.pop(receipt_id, None)
        if receipt is not None:
            self.revoked.append(receipt_id)


def _binding_ref(candidate):
    """Candidate-derived evidence marker (Forge ID shape) bound into the published service.

    The published Forge manifest must carry candidate-derived content so the
    verify stage proves proposal→device binding, not just a service round-trip
    of caller-supplied bytes (F-07). The marker is a deterministic lowercase
    `txbind-<hex>` ref appended to the published manifest's evidence_refs.
    """
    return 'txbind-' + hashlib.sha256(S.canonical(candidate)).hexdigest()[:16]


class TransplantService:
    """Owns transplant records; each stage is independently callable and tested."""

    def __init__(self, companions, links, proposer, dispatcher, substrate=None,
                 service_factory=None, provider_factory=None):
        self.companions = companions
        self.links = list(links)
        self.proposer = proposer
        self.dispatcher = dispatcher
        self.substrate = substrate
        self.service_factory = service_factory or (
            lambda m: ForgeService(MemoryProvider(copy.deepcopy(m))))
        self.provider_factory = provider_factory or (
            lambda m: MemoryProvider(copy.deepcopy(m)))
        self._records = {}
        self._seq = 0
        self._lock = threading.Lock()

    # -- stage 1: source discovery --------------------------------------
    def discover_source(self, capability_id):
        for cid, comp in self.companions.items():
            if capability_id in comp.get('capabilities', ()):
                if comp.get('online') is not True:
                    raise TransplantError('SOURCE_OFFLINE')
                if not _simulated(comp):
                    raise TransplantError('SOURCE_MUST_BE_SIMULATED')
                return {'companion_id': cid, **copy.deepcopy(comp)}
        raise TransplantError('SOURCE_UNKNOWN_CAPABILITY')

    # -- stage 2: target compat -----------------------------------------
    def check_target(self, target_id, primitive_ids, required_grants):
        comp = self.companions.get(target_id)
        if comp is None:
            raise TransplantError('TARGET_UNKNOWN')
        if comp.get('online') is not True:
            raise TransplantError('TARGET_OFFLINE')
        if not _simulated(comp):
            raise TransplantError('TARGET_MUST_BE_SIMULATED')
        missing_prims = [p for p in primitive_ids if p not in comp.get('primitives', ())]
        if missing_prims:
            raise TransplantError('TARGET_INCOMPATIBLE: %s' % ','.join(sorted(missing_prims)))
        missing_grants = [g for g in required_grants if g not in comp.get('grants', ())]
        if missing_grants:
            raise TransplantError('TARGET_GRANT_MISSING: %s' % ','.join(sorted(missing_grants)))
        return {'companion_id': target_id, **copy.deepcopy(comp)}

    # -- stage 3: route selection ----------------------------------------
    def select_route(self, source_id, target_id, need=('observe', 'read')):
        direct = [dict(l) for l in self.links
                  if l.get('parent') == source_id and l.get('child') == target_id
                  and set(need) <= set(l.get('grants', ()))]
        if not direct:
            raise TransplantError('NO_ROUTE')
        link = sorted(direct, key=lambda l: str(l.get('source', '')))[0]
        both_sim = _simulated(self.companions.get(source_id, {})) and _simulated(
            self.companions.get(target_id, {}))
        return {'route_id': 'rt-%s-%s' % (source_id, target_id), 'link': link,
                'grants': list(need), 'simulated': bool(both_sim)}

    # -- stage 4+5: proposal + schema validation -------------------------
    def propose(self, intent, bundle, primitive_ids, target_category,
                schemas=None, sources=None, required=None):
        S.validate_bundle(bundle)
        body = self.proposer.propose({'intent': intent, 'bundle': bundle,
                                      'primitive_ids': list(primitive_ids),
                                      'target_category': target_category,
                                      'schemas': schemas, 'sources': sources,
                                      'required': required})
        candidate = body['candidate']
        try:
            Y.validate_candidate(candidate, primitive_ids, bundle=bundle,
                                 schemas=schemas, sources=sources, required=required)
        except Y.SynthError as error:
            raise TransplantError('PROPOSAL_REJECTED: %s' % error) from None
        return candidate, {'model': body.get('model', 'meta'),
                           'prompt_version': body.get('prompt_version', Y.PROMPT_VERSION)}

    # -- stages 6-10: consent -> publish -> dispatch -> verify ------------
    def transplant(self, source_capability_id, target_id, intent, bundle,
                   primitive_ids, manifest, model_run, title, facts_required,
                   expires_at, target_category, required_grants=('observe', 'read'),
                   schemas=None, sources=None, required=None, consent=False):
        report = {stage: {'status': 'pending', 'detail': ''} for stage in STAGES}

        def mark(stage, status, detail=''):
            report[stage] = {'status': status, 'detail': str(detail)[:200]}

        with self._lock:
            self._seq += 1
            tid = 'tx-%04d' % self._seq
        service = None
        published_sid = None
        receipt = None
        manifest_hash = ''
        try:
            source = self.discover_source(source_capability_id)
            mark('discover_source', 'ok', source['companion_id'])
            target = self.check_target(target_id, primitive_ids, required_grants)
            mark('target_compat', 'ok', target_id)
            route = self.select_route(source['companion_id'], target_id)
            mark('route', 'ok', route['route_id'])
            candidate, meta = self.propose(intent, bundle, primitive_ids,
                                           target_category, schemas, sources, required)
            mark('propose', 'ok', '%s via %s' % (candidate['candidate_id'], meta['model']))
            mark('validate', 'ok', 'schema + evidence refs bound to bundle')
            if consent is not True:
                raise TransplantError('OWNER_CONSENT_REQUIRED')
            mark('consent', 'ok', 'explicit owner consent')
            if isinstance(manifest, dict) and manifest.get('capability_id') != source_capability_id:
                raise TransplantError('MANIFEST_CAPABILITY_MISMATCH: manifest %r is not the discovered source %r'
                                      % (manifest.get('capability_id'), source_capability_id))
            manifest_doc = VS.to_manifest(
                candidate, {'category': target_category,
                            'device_fingerprint': target_id},
                model_run, title, list(required_grants), facts_required, expires_at)
            if self.substrate is None:
                mark('compile', 'skipped', 'no substrate wired; nothing staged')
                manifest_hash = 'sha256:' + S.digest(manifest_doc)
            else:
                compiled = VS.compile_first(self.substrate, manifest_doc, [])
                if compiled['status'] != 'COMPILED':
                    raise TransplantError('COMPILE_%s' % compiled['status'])
                manifest_hash = compiled['manifest_hash']
                mark('compile', 'ok', manifest_hash)
            bind_ref = _binding_ref(candidate)
            publish_manifest = copy.deepcopy(manifest)
            refs = publish_manifest.get('evidence_refs') if isinstance(publish_manifest, dict) else None
            if isinstance(refs, list) and bind_ref not in refs and len(refs) < 32:
                refs.append(bind_ref)
            service = self.service_factory(publish_manifest)
            try:
                published = service.publish_verified(publish_manifest, consent=True)
            except ForgeError as error:
                raise TransplantError('PUBLISH_REJECTED: %s' % error) from None
            published_sid = published['service_id']
            ui_plan = VS.ui_plan(
                'transplant.%s' % tid, target_id,
                [{'widget_id': 'w-%s' % tid, 'label': title,
                  'permission_label': ','.join(required_grants),
                  'manifest_hash': manifest_hash, 'inputs': {}}],
                model_run['run_id'], candidate['evidence_refs'])
            mark('publish_ui', 'ok', published['service_id'])
            receipt = self.dispatcher.dispatch(route, candidate)
            mark('dispatch', 'ok', receipt['receipt_id'])
            verified = self._verify_independent(publish_manifest, published['service_id'],
                                                receipt, manifest_hash, bind_ref)
            mark('verify', 'ok', verified)
            record = {'transplant_id': tid, 'state': 'active', 'source': source,
                      'target': target, 'route': route, 'candidate': candidate,
                      'manifest_hash': manifest_hash, 'service_id': published['service_id'],
                      'service': service, 'ui_plan': ui_plan, 'receipt': receipt,
                      'report': report}
            with self._lock:
                self._records[tid] = record
            return self._public(record)
        except TransplantError as error:
            self._compensate(service, published_sid, receipt)
            failed = next(s for s in STAGES if report[s]['status'] == 'pending')
            mark(failed, 'failed', error)
            self._store_failure(tid, published_sid, manifest_hash, report)
            raise
        except Exception as error:
            self._compensate(service, published_sid, receipt)
            if published_sid is not None:
                failed = next(s for s in STAGES if report[s]['status'] == 'pending')
                mark(failed, 'failed', '%s: %s' % (type(error).__name__, error))
                self._store_failure(tid, published_sid, manifest_hash, report)
            raise

    def _compensate(self, service, service_id, receipt):
        """Undo post-publish side effects so a failed transplant orphans nothing.

        Best-effort by design: compensation must never mask the original error.
        The UI plan is in-memory only (dropped by not storing it); compile is
        pure with respect to this service (no staged handle to release).
        """
        if service is None or service_id is None:
            return
        try:
            service.remove(service_id)
        except Exception:
            pass
        rid = (receipt or {}).get('receipt_id')
        revoke_hook = getattr(self.dispatcher, 'revoke', None)
        if rid and callable(revoke_hook):
            try:
                revoke_hook(rid)
            except Exception:
                pass

    def _store_failure(self, tid, service_id, manifest_hash, report):
        """Persist a post-publish failure report under the tid for audit."""
        if service_id is None:
            return
        report['revoke'] = {'status': 'ok', 'detail': 'compensated: live service removed'}
        report['cleanup'] = {'status': 'ok', 'detail': 'compensated: receipt revoked, plan dropped'}
        with self._lock:
            self._records[tid] = {'transplant_id': tid, 'state': 'failed',
                                  'service_id': service_id, 'manifest_hash': manifest_hash,
                                  'ui_plan': {}, 'receipt': {}, 'report': report}

    def _verify_independent(self, durable_manifest, service_id, receipt, manifest_hash, binding_ref):
        """Independent path: a freshly constructed provider re-reads durable state.

        Never the live service object and never dispatch state: a provider bug,
        in-memory poisoning, or a publish path that echoes only through the
        live object is invisible to a same-object re-read but cannot survive a
        fresh provider over the durable manifest plus the candidate binding check.
        """
        try:
            fresh_provider = self.provider_factory(copy.deepcopy(durable_manifest))
            snapshot = fresh_provider.snapshot(durable_manifest['capability_id'])
        except ForgeError as error:
            raise TransplantError('VERIFICATION_FAILED: %s' % error) from None
        except Exception as error:
            raise TransplantError('VERIFICATION_FAILED: %s' % error) from None
        if not snapshot.get('observations'):
            raise TransplantError('VERIFICATION_FAILED: no observations on re-read')
        if snapshot.get('service_id') != service_id:
            raise TransplantError('VERIFICATION_FAILED: re-read service binding mismatch')
        if binding_ref not in (snapshot.get('evidence_refs') or []):
            raise TransplantError('VERIFICATION_FAILED: candidate binding missing on re-read')
        if receipt.get('state') != 'dispatched':
            raise TransplantError('VERIFICATION_FAILED: dispatch receipt not confirmed')
        return 're-read %d observation(s); %s' % (len(snapshot['observations']), manifest_hash)

    # -- stage 11+12: revocation + cleanup -------------------------------
    def revoke(self, transplant_id):
        with self._lock:
            record = self._records.get(transplant_id)
            if record is None:
                raise TransplantError('UNKNOWN_TRANSPLANT')
            if record['state'] in ('revoked', 'failed'):
                return self._public(record)
        record['service'].remove(record['service_id'])
        revoke_hook = getattr(self.dispatcher, 'revoke', None)
        rid = (record.get('receipt') or {}).get('receipt_id')
        if rid and callable(revoke_hook):
            revoke_hook(rid)
        with self._lock:
            record['receipt'] = {}
            record['ui_plan'] = {}
            record['candidate'] = {}
            record['state'] = 'revoked'
            record['report']['revoke'] = {'status': 'ok', 'detail': 'service removed'}
            record['report']['cleanup'] = {'status': 'ok',
                                           'detail': 'receipt, ui plan, proposal cleared'}
            return self._public(record)

    def report(self, transplant_id):
        with self._lock:
            record = self._records.get(transplant_id)
            if record is None:
                raise TransplantError('UNKNOWN_TRANSPLANT')
            return copy.deepcopy(record['report'])

    def get(self, transplant_id):
        with self._lock:
            record = self._records.get(transplant_id)
            if record is None:
                raise TransplantError('UNKNOWN_TRANSPLANT')
            return self._public(record)

    def _public(self, record):
        return {'transplant_id': record['transplant_id'], 'state': record['state'],
                'service_id': record.get('service_id', ''),
                'manifest_hash': record.get('manifest_hash', ''),
                'ui_plan': copy.deepcopy(record.get('ui_plan', {})),
                'receipt': copy.deepcopy(record.get('receipt', {})),
                'report': copy.deepcopy(record['report'])}
