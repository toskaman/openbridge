"""Explicit synthetic fixture, not evidence of hardware discovery."""
import time

def manifest(now=None):
    return {'version':1,'service_id':'ble-observations','capability_id':'tv.ble.observations','device_id':'beacon-demo','relay_id':'tv-demo','source':'RELAY:tv-demo','status':'SIMULATED_VERIFIED','verified':True,'operation':'read_observations','permissions':['observe','read'],'available':True,'device_present':True,'identity_conflict':False,'observed_at':time.time() if now is None else now,'max_age_seconds':120,'evidence_refs':['evidence-relay','evidence-signal'],'observations':[{'observation_id':'obs-1','name':'Demo beacon','rssi_dbm':-62,'manufacturer_data_hex':'0102'}],'simulation':True}
