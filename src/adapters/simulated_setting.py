"""Persistent synthetic setting for transaction and restart demonstrations only."""
from contextlib import closing
from pathlib import Path
import sqlite3


class SimulatedSetting:
    source='SIMULATED'
    identity='simulated-screen-setting'

    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS setting (id INTEGER PRIMARY KEY CHECK(id=1), value INTEGER NOT NULL)')
            db.execute('INSERT OR IGNORE INTO setting VALUES(1,30)')

    def read_setting(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT value FROM setting WHERE id=1').fetchone()[0]

    def write_setting(self,value):
        if type(value) is not int or not 0 < value <= 86400:
            raise ValueError('Invalid synthetic setting')
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE setting SET value=? WHERE id=1',(value,))
