"""Narrow writer: disable/re-enable one allowlisted optional utility app for Android user 0 only."""
import hashlib
from src.adapters.android_timeout import AndroidTimeoutSetting

# Engine values = Android COMPONENT_ENABLED_STATE + 1 (engine requires positive integers).
DEFAULT=1
ENABLED=2
DISABLED=4
CODES={0:DEFAULT,1:ENABLED,3:DISABLED}
# Optional, data-preserving utility apps only. Never system, security, messaging, banking or Google services.
ALLOWED_PACKAGES=frozenset({'org.nixgame.ruler','one.vik.stopwatch','com.miui.compass'})


class AndroidPackageState(AndroidTimeoutSetting):
    source='ADB'
    allowed_targets=(DEFAULT,ENABLED,DISABLED)
    write_transports=('USB','WIFI','EMULATOR')  # ADB authorization is the trust boundary; Wi-Fi must already be paired by the owner
    field='package_enabled_state'

    def __init__(self,adb,handle,package):
        if package not in ALLOWED_PACKAGES:
            raise ValueError('Package is not on the reviewed optional-app allowlist')
        self.package=package
        super().__init__(adb,handle)
        sdk=self._command('shell','getprop','ro.build.version.sdk')
        self.sdk=int(sdk) if sdk.isdigit() else 0
        self.identity='android-package-'+hashlib.sha256((self._serial+'\0'+self._fingerprint+'\0'+package).encode()).hexdigest()

    def _preflight(self):
        super()._preflight()
        user=self._command('shell','am','get-current-user')
        if user!='0':
            raise ValueError('The active Android user is not user 0; refusing to act on another profile')

    def can_restore(self,value):
        # `pm default-state` exists from Android 9 (API 28). Before that the default code cannot be re-created exactly.
        return value!=DEFAULT or self.sdk>=28

    def _listed(self,flag):
        out=self._command('shell','pm','list','packages',flag,self.package)
        return f'package:{self.package}' in out.split()

    def read_setting(self):
        self._preflight()
        enabled,disabled=self._listed('-e'),self._listed('-d')
        dump=self._command('shell','dumpsys','package',self.package)
        lines=dump.replace('\r','').split('\n')
        start=next((i for i,l in enumerate(lines) if l.strip().startswith('User 0:')),None)
        if start is None or enabled==disabled:
            raise ValueError('Package state is missing or inconsistent; no write is safe')
        block=' '.join(lines[start:start+2])
        code=next((int(t.split('=')[1]) for t in block.split() if t.startswith('enabled=') and t.split('=')[1].isdigit()),None)
        if code not in CODES or (CODES[code]==DISABLED)!=disabled:
            raise ValueError('Package state is missing or inconsistent; no write is safe')
        return CODES[code]

    def write_setting(self,value):
        if type(value) is not int or value not in (DEFAULT,ENABLED,DISABLED):
            raise ValueError('Invalid package state')
        self._preflight()
        verb,expected={DISABLED:('disable-user','disabled-user'),ENABLED:('enable','enabled'),DEFAULT:('default-state','default')}[value]
        out=self._command('shell','pm',verb,'--user','0',self.package)
        if f'new state: {expected}' not in out:
            raise ValueError('Android did not confirm the package state change')
