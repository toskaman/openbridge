"""V4 CapabilityGapDetector: KNOWN_EXISTING vs NEW_POSSIBLE vs NO_ROUTE (P0 heuristic)."""
READ_ONLY = {'read_facts'}


def classify(intent_text, target_category, skills, primitive_ids):
    words = set(intent_text.lower().split())
    for s in skills:
        verb = s['skill_id'].split('.')[-1]
        if verb in words and target_category in s.get('targets', ()):
            return ('KNOWN_EXISTING_SKILL', s['skill_id'])
    if set(primitive_ids) - READ_ONLY:
        return ('NEW_SKILL_POSSIBLE', 'no registered skill; action primitives exist')
    return ('NO_AUTHORIZED_ROUTE', 'read-only primitives only')
