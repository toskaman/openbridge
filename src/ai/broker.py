"""Shared primitives for model calls (local models and manually connected providers).

OpenBridge ships no paid model. The hosted Meta "Muse Spark" broker, its promotional-credit
ledger and every paid code path were removed; owners who want a hosted model connect their
own provider by hand (src/ai/custom_provider.py, `openbridge ai add`).
"""
from urllib.request import HTTPRedirectHandler

# Numeric facts a model may see for an advisory review (local providers only).
ALLOWED_FACTS = {'battery_percent', 'storage_free_gb', 'screen_timeout_seconds'}


class ModelBlocked(ValueError):
    """The request did not pass the runtime boundary (registry, schema, consent or transport)."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        # Never return None: urllib would swallow the redirect and either propagate a raw
        # HTTPError or parse the 302 body as provider output, depending on version (N-24).
        # Credentials are never forwarded to another host.
        raise ModelBlocked('provider redirected (refused, credential not forwarded)')
