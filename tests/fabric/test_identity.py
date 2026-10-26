import unittest
from src.fabric.contracts import Identifier, DeviceObservation, Link, opaque, mac_is_randomized, now
from src.fabric.registry import Registry

SALT=b'test-salt'
def strong(kind,raw):return Identifier(kind,opaque(kind,raw,SALT),True)
def obs(k,v,src,verified=True):return DeviceObservation(k,v,src,'USB',now(),verified)


class IdentityTests(unittest.TestCase):
    def test_same_android_over_usb_and_wifi_is_one_device_with_two_links(self):
        r=Registry()
        a=r.upsert([strong('android_serial','R5CT1')],category='phone',observations=[obs('model','Pixel','ADB')])
        b=r.upsert([strong('android_serial','R5CT1')],observations=[obs('battery_percent',80,'ADB')],weak=[('ip','192.168.1.20')])
        self.assertEqual(a,b)
        r.link(Link('pc',a,'USB',('read','control'),'ADB'));r.link(Link('pc',a,'WIFI',('read','control'),'ADB'))
        snap=r.snapshot();self.assertEqual(len(snap['devices']),1);self.assertEqual(len(snap['links']),2)

    def test_same_device_two_ips_merges_only_by_strong_id(self):
        r=Registry()
        a=r.upsert([strong('freebox_uid','u1')],weak=[('ip','192.168.1.254')])
        b=r.upsert([strong('freebox_uid','u1')],weak=[('ip','192.168.0.254')])
        self.assertEqual(a,b)

    def test_reassigned_ip_does_not_merge_two_devices(self):
        r=Registry()
        a=r.upsert([strong('android_serial','A')],weak=[('ip','192.168.1.50')])
        b=r.upsert([strong('android_serial','B')],weak=[('ip','192.168.1.50')])
        self.assertNotEqual(a,b);self.assertIn(sorted((a,b)),r.snapshot()['possible_duplicates'])

    def test_two_devices_of_same_model_stay_separate(self):
        r=Registry()
        a=r.upsert([strong('android_serial','A')],observations=[obs('model','2107113SG','ADB')])
        b=r.upsert([strong('android_serial','B')],observations=[obs('model','2107113SG','ADB')])
        self.assertNotEqual(a,b)

    def test_randomized_mac_is_never_strong(self):
        self.assertTrue(mac_is_randomized('da:a1:19:00:00:01'));self.assertFalse(mac_is_randomized('00:1a:2b:3c:4d:5e'))
        self.assertTrue(mac_is_randomized('garbage'))

    def test_incomplete_identity_creates_separate_unmerged_devices(self):
        r=Registry()
        a=r.upsert([],weak=[('mdns_name','Living Room TV')]);b=r.upsert([],weak=[('mdns_name','Living Room TV')])
        self.assertNotEqual(a,b);self.assertIn(sorted((a,b)),r.snapshot()['possible_duplicates'])

    def test_conflicting_strong_identifiers_refuse_merge(self):
        r=Registry()
        a=r.upsert([strong('android_serial','A')]);b=r.upsert([strong('mac_global','00:11:22:33:44:55')])
        c=r.upsert([strong('android_serial','A'),strong('mac_global','00:11:22:33:44:55')])
        self.assertNotIn(c,(a,b));self.assertEqual(len(r.snapshot()['possible_duplicates']),2)

    def test_sources_are_kept_and_verified_reads_win(self):
        r=Registry()
        k=r.upsert([strong('android_serial','A')],observations=[obs('model','TV-X','FREEBOX_API',verified=False),obs('model','TV-X2','ADB')])
        f=r.snapshot()['devices'][0]['facts']['model']
        self.assertEqual(f['value'],'TV-X2');self.assertEqual(f['sources'],['ADB','FREEBOX_API'])

    def test_raw_identifiers_never_in_snapshot(self):
        r=Registry();r.upsert([strong('android_serial','RAW_SERIAL_123')])
        self.assertNotIn('RAW_SERIAL_123',str(r.snapshot()))

    def test_unknown_link_grant_rejected(self):
        with self.assertRaises(ValueError):Registry().link(Link('pc','x','LAN',('admin',),'X'))


class CategoryAndHintTests(unittest.TestCase):
    def test_specific_category_wins_and_hints_exposed(self):
        r=Registry()
        a=r.upsert([strong('mdns_host','lg.local')],category='iot');r.upsert([strong('mdns_host','lg.local')],category='media')
        b=r.upsert([],category='tv',weak=[('ip','192.168.1.40')]);c=r.upsert([],category='media',weak=[('ip','192.168.1.40')])
        snap={d['key']:d for d in r.snapshot()['devices']}
        self.assertEqual(snap[a]['category'],'media');self.assertEqual(snap[b]['possibly_same_as'],[c])
