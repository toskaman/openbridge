import os
TV=os.environ.get('OPENBRIDGE_TV_ADDR','');PHONE=os.environ.get('OPENBRIDGE_PHONE_SERIAL','')
"""One-off: record into the session journal the changes made manually (via the dev bridge) during the 27 Oct TV tests,
so the owner can restore them through the product's "Finish session" flow."""
from src.fabric.session import SessionJournal
j=SessionJournal()
j.record('system_package_enabled','Android TV',{'serial':TV,'package':'com.android.bluetooth'},3,1)
j.record('companion_installed','Android TV',{'serial':TV},'not installed','installed')
j.record('companion_installed','Phone (USB)',{'serial':PHONE},'not installed','installed')
j.record('adb_network_connected','Android TV',{'address':TV},'not connected','connected')
print(len(j.open_changes()),'open changes')
