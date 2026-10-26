"""Narrow experimental writer for one owned USB phone's screen timeout only."""
import hashlib
import re


class AndroidTimeoutSetting:
    source='ADB'
    write_transports=('USB',)

    def __init__(self,adb,handle):
        self._adb=adb
        devices=adb.discover()['devices']
        device=next((d for d in devices if d['id']==handle and d['state']=='device' and d['transport'] in self.write_transports),None)
        if device is None:
            raise ValueError('An authorized USB phone is required')
        self._serial=next(key for key,value in adb._handles.items() if value==handle)
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}',self._serial):
            raise ValueError('Unsupported device identifier')
        self._fingerprint=self._read_fingerprint()
        self.identity='android-timeout-'+hashlib.sha256((self._serial+'\0'+self._fingerprint).encode()).hexdigest()

    def _command(self,*args):
        return self._adb._run(['-s',self._serial,*args]).strip()

    def _read_fingerprint(self):
        value=self._command('shell','getprop','ro.build.fingerprint')
        if not value or len(value)>1024 or any(ord(c)<32 for c in value):
            raise ValueError('Device build identity unavailable')
        return value

    def _preflight(self):
        devices=self._adb.discover()['devices']
        handle=self._adb._handles.get(self._serial)
        if not any(d['id']==handle and d['state']=='device' and d['transport'] in self.write_transports for d in devices):
            raise ValueError('Owned USB phone unavailable or no longer authorized')
        if self._command('get-state') != 'device' or self._read_fingerprint()!=self._fingerprint:
            raise ValueError('Device identity or authorization changed')

    def read_setting(self):
        self._preflight()
        value=self._command('shell','settings','get','system','screen_off_timeout')
        if not value.isdigit() or not 1000 <= int(value) <= 86400000 or int(value)%1000:
            raise ValueError('The original timeout cannot be restored with exact integer-second precision')
        return int(value)//1000

    def write_setting(self,value):
        # The transaction engine limits proposals; this bound also permits exact snapshot restoration.
        if type(value) is not int or not 0 < value <= 86400:
            raise ValueError('Invalid screen-timeout value')
        self._preflight()
        self._command('shell','settings','put','system','screen_off_timeout',str(value*1000))
