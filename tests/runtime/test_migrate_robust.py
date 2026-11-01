"""E1 robustness (A5): migrate spanning lock + generation-aware rollback.

- apply/rollback hold one spanning lock across their two set_controls, and
  apply re-checks the source after the destination install (an interleaving
  owner edit 409s with a receipt instead of silently changing the move);
- rollback compares the recorded generations and refuses (409) when the
  destination holds identical-looking controls created after the migration
  instead of pruning the owner's new controls.
"""
import threading
import time
import unittest

from src.runtime import migrate as M
from tests.runtime.test_migrate import Base


class SpanningLock(Base):
    def test_both_phases_run_under_the_spanning_lock(self):
        orig = self.rc.set_controls
        seen = []

        def watching(body):
            seen.append(M._LOCK.locked())
            return orig(body)

        self.rc.set_controls = watching
        try:
            receipt = M.apply(self.server, self.propose_volumes()['proposal'], True)
            M.rollback(self.server, receipt, True)
        finally:
            self.rc.set_controls = orig
        self.assertEqual(seen, [True, True, True, True])

    def test_owner_edit_between_phases_409s_with_receipt(self):
        orig = self.rc.set_controls
        state = {'n': 0, 'owner': False}

        def watching(body):
            if state['owner']:
                return orig(body)
            out = orig(body)
            state['n'] += 1
            if state['n'] == 1:
                # Owner re-grants the source right after our destination
                # install lands: the old control ids are gone.
                state['owner'] = True
                try:
                    tv = self.keys['tv']
                    orig({'relay_id': 'r-watch', 'controls': [
                        {'label': 'YouTube', 'skill_id': 'app_launch', 'target': tv,
                         'params': {'package': 'com.google.android.youtube.tv'}}],
                        'consent': True})
                finally:
                    state['owner'] = False
            return out

        self.rc.set_controls = watching
        try:
            with self.assertRaises(M.MigrationError) as cm:
                M.apply(self.server, self.propose_volumes()['proposal'], True)
        finally:
            self.rc.set_controls = orig
        self.assertEqual(cm.exception.status, 409)
        self.assertIsNotNone(cm.exception.receipt)
        self.assertIn('migration_id', cm.exception.receipt)
        # Destination holds the installed copy; the source keeps exactly the
        # owner's version (nothing silently removed, nothing lost).
        self.assertEqual(self.labels('r-tv'), ['Chrome', 'TV volume +', 'TV volume -'])
        self.assertEqual(self.labels('r-watch'), ['YouTube'])


class GenerationAwareRollback(Base):
    def _dst_defs(self):
        return [{'label': g['label'], 'skill_id': g['skill_id'], 'target': g.get('target'),
                 'params': dict(g.get('params') or {})}
                for _, g in sorted(self.rc.grants['r-tv'].items())]

    def test_def_key_collision_on_destination_blocks_rollback(self):
        # set_controls dedups identical defs (deterministic ids), so a true
        # def_key collision — two identical-looking controls under different
        # ids — can only arise out-of-band. The guard must refuse (409)
        # rather than prune ambiguously-owned controls.
        receipt = M.apply(self.server, self.propose_volumes()['proposal'], True)
        grants = self.rc.grants['r-tv']
        victim = next(cid for cid, g in grants.items() if g['label'] == 'TV volume +')
        grants['ctl-injected-g99'] = dict(grants[victim])
        self.rc._grant_versions['r-tv'] += 1  # out-of-band write drifted the gen
        with self.assertRaises(M.MigrationError) as cm:
            M.rollback(self.server, receipt, True)
        self.assertEqual(cm.exception.status, 409)
        # Refused before any write: both sides untouched.
        self.assertEqual(self.labels('r-tv'),
                         ['Chrome', 'TV volume +', 'TV volume +', 'TV volume -'])
        self.assertEqual(len(self.rc.grants['r-tv']), 4)
        self.assertEqual(self.labels('r-watch'), ['YouTube'])

    def test_distinct_owner_control_still_rolls_back(self):
        receipt = M.apply(self.server, self.propose_volumes()['proposal'], True)
        tv = self.keys['tv']
        self.rc.set_controls({'relay_id': 'r-tv', 'controls': self._dst_defs() + [
            {'label': 'New', 'skill_id': 'app_launch', 'target': tv,
             'params': {'package': 'com.example.new'}}], 'consent': True})
        res = M.rollback(self.server, receipt, True)
        self.assertTrue(res['rolled_back'])
        self.assertEqual(self.labels('r-tv'), ['Chrome', 'New'])
        self.assertEqual(self.labels('r-watch'), ['TV volume +', 'TV volume -', 'YouTube'])

    def test_second_rollback_stays_a_safe_noop(self):
        receipt = M.apply(self.server, self.propose_volumes()['proposal'], True)
        M.rollback(self.server, receipt, True)
        M.rollback(self.server, receipt, True)
        self.assertEqual(self.labels('r-watch'), ['TV volume +', 'TV volume -', 'YouTube'])
        self.assertEqual(self.labels('r-tv'), ['Chrome'])


class ConcurrentMigrations(Base):
    def test_opposite_moves_lose_no_controls(self):
        p1 = M.propose(self.server, source='r-watch', target='r-tv', match='volume')['proposal']
        p2 = M.propose(self.server, source='r-tv', target='r-watch', match='Chrome')['proposal']
        orig = self.rc.set_controls

        def slow(body):
            time.sleep(0.01)
            return orig(body)

        self.rc.set_controls = slow
        outcomes = []
        lock = threading.Lock()

        def run(proposal):
            try:
                receipt = M.apply(self.server, proposal, True)
            except M.MigrationError as e:
                with lock:
                    outcomes.append(('error', e.status))
            else:
                with lock:
                    outcomes.append(('ok', receipt))

        threads = [threading.Thread(target=run, args=(p,)) for p in (p1, p2)]
        try:
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        finally:
            self.rc.set_controls = orig
        self.assertEqual(len(outcomes), 2)
        # Exactly one move wins; the loser 409s on stale source ids with no
        # partial install (its pre-check runs after the winner's writes).
        winners = [r for o, r in outcomes if o == 'ok']
        errors = [s for o, s in outcomes if o == 'error']
        self.assertEqual(len(winners), 1)
        self.assertEqual(errors, [409])
        if winners[0]['migrated'][0]['label'].startswith('TV volume'):
            self.assertEqual(self.labels('r-watch'), ['YouTube'])
            self.assertEqual(self.labels('r-tv'), ['Chrome', 'TV volume +', 'TV volume -'])
        else:
            self.assertEqual(sorted(self.labels('r-watch')),
                             ['Chrome', 'TV volume +', 'TV volume -', 'YouTube'])
            self.assertEqual(self.labels('r-tv'), [])


if __name__ == '__main__':
    unittest.main()
