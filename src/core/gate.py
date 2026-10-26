"""Deterministic action gate: the model proposes, this code decides. Absent proof => DENY."""
from src.adapters.android_package import ALLOWED_PACKAGES, DISABLED

ALLOW_WITH_CONSENT='REVIEW_REQUIRED'


def evaluate(proposal,candidates):
    """candidates: {package: engine_state} for allowlisted apps actually installed on the device."""
    reasons=[]
    action=proposal.get('action') if isinstance(proposal,dict) else None
    if action=='inspect_only':
        return {'decision':'NO_ACTION','reasons':['Model proposed observation only; nothing to execute.']}
    if action!='disable_optional_app':
        return {'decision':'DENY','reasons':['Unknown or unsupported action.']}
    package=proposal.get('package')
    if package not in ALLOWED_PACKAGES:reasons.append('Package is not on the reviewed optional-app allowlist.')
    elif package not in candidates:reasons.append('Package is not installed or its state could not be verified.')
    elif candidates[package]==DISABLED:reasons.append('Package is already disabled; nothing reversible to do.')
    if reasons:return {'decision':'DENY','reasons':reasons}
    return {'decision':ALLOW_WITH_CONSENT,'reasons':[
        'Allowlisted optional app, installed, currently enabled.',
        'Reversible: exact Android enabled-state code is snapshotted before any change.',
        'Owner consent is required before execution.']}
