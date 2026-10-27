"""Explicit optional isolated CPU Meta route; no automatic fallback or download."""
from src.ai.glimmer import GlimmerBroker
from src.forge.compiler import ForgeError
import time

class IsolatedGlimmerCPU(GlimmerBroker):
    endpoint='http://127.0.0.1:11439'
    provider='Ollama isolated local CPU'
    options={'temperature':0,'num_gpu':0,'num_ctx':1024,'num_batch':32,'num_thread':4,'num_predict':384,'use_mmap':True}
    timeout=180
    keep_alive='5m'

    def _control(self,release):
        if not self.ready():raise ForgeError('META_UNAVAILABLE')
        started=time.monotonic()
        payload={'model':self.model_id,'stream':False,'keep_alive':0 if release else self.keep_alive,'options':dict(self.options),**self.extra}
        try:
            result=self.chat(payload)
            if result.get('model')!=self.model_id or result.get('done') is not True or result.get('done_reason')!=('unload' if release else 'load'):
                raise ForgeError('MODEL_CONTROL_IDENTITY_OR_STATE_INVALID')
            message=result.get('message') or {}
            if not isinstance(message,dict) or message.get('content') or message.get('thinking') or message.get('tool_calls') or result.get('response'):
                raise ForgeError('MODEL_CONTROL_UNEXPECTED_GENERATION')
            for key in ('prompt_eval_count','eval_count'):
                value=result.get(key)
                if value is not None and (type(value) is not int or value!=0):raise ForgeError('MODEL_CONTROL_UNEXPECTED_GENERATION')
            if not self.ready():raise ForgeError('META_DIGEST_CHANGED')
            return {'state':'released' if release else 'ready','model_id':self.model_id,'model_digest':self.model_digest,
                'keep_alive_seconds':0 if release else 300,'tokens_generated':0,'provider_cost_usd':0.0,
                'device_data_read':False,'elapsed_ms':round(1000*(time.monotonic()-started))}
        except ForgeError:raise
        except Exception:raise ForgeError('MODEL_CONTROL_FAILED') from None

    def prepare(self):return self._control(False)
    def release(self):return self._control(True)
