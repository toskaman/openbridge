"""Pure/fake checks only: never starts hardware, a model, or a browser."""
import unittest
from dev.forge_workspace_journey import (
    companion_unpaired, forward_created_by_journey, remove_owned_forward,
    read_companion_xml, permission_snapshot, JourneyBlocked,
)


class FakeAndroid:
    def __init__(self, lines='', fail_cat=False):
        self.lines, self.fail_cat, self.calls = lines, fail_cat, []

    def _run(self, args):
        self.calls.append(args)
        if args == ['forward', '--list']:
            return self.lines
        if 'cat' in args:
            if self.fail_cat:
                raise ValueError('private failure must not reach receipts')
            return '<hierarchy/>'
        return ''


class WorkspaceJourneyTests(unittest.TestCase):
    def row(self, value, package='fr.openbridge.companion'):
        return f'<hierarchy><node package="{package}"><node text="Paired with a PC" package="{package}"/><node text="{value}" package="{package}"/></node></hierarchy>'

    def test_unpairing_requires_exact_companion_row(self):
        self.assertIs(companion_unpaired(self.row('Not yet')), True)
        self.assertIs(companion_unpaired(self.row('Yes')), False)
        self.assertIsNone(companion_unpaired(self.row('Not yet', 'other.app')))
        self.assertIsNone(companion_unpaired('<bad'))
        self.assertIsNone(companion_unpaired('<hierarchy><node text="Not yet"/></hierarchy>'))
        self.assertIsNone(companion_unpaired('<hierarchy>'+self.row('Not yet')+self.row('Yes')+'</hierarchy>'))

    def test_unrelated_not_yet_cannot_claim_remote_unpairing(self):
        xml='<hierarchy><node><node text="Paired with a PC" package="fr.openbridge.companion"/><node text="Yes" package="fr.openbridge.companion"/></node><node text="Not yet"/></hierarchy>'
        self.assertIs(companion_unpaired(xml), False)

    def test_forward_ownership_is_exact_and_existing_forward_is_preserved(self):
        self.assertTrue(forward_created_by_journey('', 'serial'))
        self.assertFalse(forward_created_by_journey('serial tcp:47800 tcp:47800', 'serial'))
        with self.assertRaises(JourneyBlocked):
            forward_created_by_journey('other tcp:47800 tcp:47800', 'serial')
        android=FakeAndroid('serial tcp:47800 tcp:47800')
        self.assertTrue(remove_owned_forward(android, 'serial', False))
        self.assertEqual(android.calls, [])
        self.assertTrue(remove_owned_forward(android, 'serial', True))
        self.assertIn(['-s', 'serial', 'forward', '--remove', 'tcp:47800'], android.calls)

    def test_changed_forward_is_never_removed(self):
        android=FakeAndroid('other tcp:47800 tcp:47800')
        self.assertFalse(remove_owned_forward(android, 'serial', True))
        self.assertEqual(android.calls, [['forward', '--list']])

    def test_ui_xml_temporary_file_is_removed_on_success_and_failure(self):
        for failed in (False, True):
            android=FakeAndroid(fail_cat=failed)
            if failed:
                with self.assertRaises(ValueError): read_companion_xml(android, 'serial')
            else:
                self.assertEqual(read_companion_xml(android, 'serial'), '<hierarchy/>')
            self.assertEqual(android.calls[-1][0:4], ['-s', 'serial', 'shell', 'rm'])
            self.assertEqual(android.calls[0][-1], android.calls[-1][-1])

    def test_permissions_are_bounded_without_raw_package_details(self):
        value=permission_snapshot('private identifier android.permission.BLUETOOTH_SCAN: granted=true\nandroid.permission.BLUETOOTH_CONNECT: granted=false')
        self.assertEqual(value, {'ACCESS_FINE_LOCATION': [], 'BLUETOOTH_SCAN': [True], 'BLUETOOTH_CONNECT': [False]})


if __name__ == '__main__': unittest.main()
