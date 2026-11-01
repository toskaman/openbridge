"""Campaign Two D2: before/after measurement for NL follow-up resolution.

Deterministic only (no model): every parse uses a FakeTransport that
abstains, so the baseline is the router's deterministic fallback alone,
and the AFTER path adds nl_followup context resolution on top.

Usage: python scripts/nl_followup_measure.py [--json]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.runtime import intent as I
from src.runtime import nl_followup as F
from src.runtime import nl_router as N

CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'tests', 'runtime', 'nl_followup_corpus.json')

DEVICES = {'dev-tv1': {'key': 'dev-tv1', 'category': 'tv', 'label': 'Living room TV'},
           'dev-vac1': {'key': 'dev-vac1', 'category': 'vacuum', 'label': 'Roborock'}}


class FakeTransport:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def __call__(self, prompt):
        self.calls.append(prompt)
        if self.error is not None:
            raise self.error
        return self.reply(prompt) if callable(self.reply) else self.reply


def abstain(outcome, targets=()):
    return {'outcome': outcome, 'skill_id': None, 'targets': list(targets),
            'params': {}, 'confidence': 0.0, 'ambiguities': [],
            'clarifying_question': None}


def resolved(skill_id, outcome, targets):
    return {'outcome': outcome, 'skill_id': skill_id, 'targets': list(targets),
            'params': {}, 'confidence': 0.9, 'ambiguities': [],
            'clarifying_question': None}


def make_prior(case):
    if not case['prior_skill']:
        return None
    return N.parse('prior turn', case['lang'], 'low',
                   FakeTransport(resolved(case['prior_skill'], 'prior turn',
                                          case['prior_targets'])), None)


def run_case(case):
    prior = make_prior(case)
    if case['prior_skill']:
        assert prior['status'] == 'resolved', case['id']
    base = N.parse(case['followup'], case['lang'], 'low',
                   FakeTransport(abstain(case['followup'])), None)
    hit = F.resolve_followup(case['followup'], case['lang'], prior, DEVICES)
    after = hit if hit is not None else base
    exp = case['expected_skill']
    if exp is None:
        ok_before = base['skill_id'] is None and base['status'] != 'resolved'
        ok_after = hit is None  # must fall through, never guess
    else:
        ok_before = base['status'] == 'resolved' and base['skill_id'] == exp
        ok_after = (after['status'] == 'resolved' and after['skill_id'] == exp
                    and after['targets'] == case['prior_targets']
                    and I.validate_intent(after) == [])
    return {'id': case['id'],
            'before': '%s/%s' % (base['status'], base['skill_id']),
            'after': '%s/%s' % (after['status'], after['skill_id']),
            'ok_before': ok_before, 'ok_after': ok_after}


def main():
    with open(CORPUS, encoding='utf-8') as fh:
        corpus = json.load(fh)
    rows = [run_case(c) for c in corpus]
    n = len(rows)
    b = sum(1 for r in rows if r['ok_before'])
    a = sum(1 for r in rows if r['ok_after'])
    summary = {'corpus': len(corpus), 'correct_before': b, 'correct_after': a,
               'accuracy_before': round(b / n, 4), 'accuracy_after': round(a / n, 4),
               'rows': rows}
    if '--json' in sys.argv:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print('NL follow-up corpus: %d cases' % n)
        print('BEFORE (router fallback only): %d/%d = %.1f%%'
              % (b, n, 100.0 * b / n))
        print('AFTER  (+ context resolution):  %d/%d = %.1f%%'
              % (a, n, 100.0 * a / n))
        for r in rows:
            flag = 'OK ' if r['ok_after'] else 'FAIL'
            print('  [%s] %-22s before=%-28s after=%s'
                  % (flag, r['id'], r['before'], r['after']))
    return 0 if a == n else 1


if __name__ == '__main__':
    sys.exit(main())
