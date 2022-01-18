from collections import defaultdict, namedtuple
import sqlite3
import logging
import contextlib
import os

User = namedtuple('User', ['username', 'password', 'permissions', 'control_point'])
RacePoint = namedtuple('RacePoint', ['timestamp', 'control_point'])
KPPoint = namedtuple('KPPoint', ['timestamp', 'racer'])


INIT_QUERY = '''CREATE TABLE IF NOT EXISTS RACE(racer_id INT,
        kpp_id TEXT,
        timestamp INT,
        user TEXT,
        PRIMARY KEY (racer_id, timestamp));
    CREATE INDEX IF NOT EXISTS index_racer ON RACE(racer_id);
    CREATE INDEX IF NOT EXISTS index_timestamp ON RACE(timestamp);
    CREATE INDEX IF NOT EXISTS index_kpp_id ON RACE(kpp_id);
    '''

EVENT_INSERT = 'INSERT INTO RACE(racer_id, kpp_id,timestamp,user) VALUES (?,?,?,?)'
ALL_EVENTS = 'SELECT racer_id, kpp_id, timestamp, user FROM RACE ORDER BY racer_id, timestamp'
MAX_EVENTS = 'SELECT racer_id, max(timestamp) FROM RACE GROUP BY racer_id'
ALL_EVENTS_RAW = 'SELECT racer_id, kpp_id, timestamp, user FROM RACE ORDER BY timestamp'
KPP_EVENTS = 'SELECT racer_id,timestamp FROM RACE WHERE kpp_id=? ORDER BY timestamp DESC'
RACER_EVENTS = 'SELECT * FROM RACE WHERE racer_id=? ORDER BY timestamp DESC'
DELETE_ALL = 'DELETE FROM RACE'

logger = logging.getLogger(__name__)

class SqliteDb:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        if not db_path.exists():
            self.init_db()
        elif not self.check_base():
            os.remove(self.db_path)
            self.init_db()
    
    def connect(self):
        return sqlite3.connect(self.db_path)
    
    def check_base(self):
        try:
            with contextlib.closing(self.connect()) as ccon:
                with ccon as con:
                    con.execute(ALL_EVENTS).fetchone()
            return True
        except:
            return False
                

    def init_db(self):
        logger.info("Init db")
        with contextlib.closing(self.connect()) as ccon:
            with ccon as con:
                con.executescript(INIT_QUERY)

    def save_event(self, racer_id, control_point, timestamp, user_id):
        with contextlib.closing(self.connect()) as ccon:
            with ccon as con:
                try:
                    con.execute(EVENT_INSERT, (racer_id, control_point, timestamp, user_id))
                except Exception:
                    logger.error(f"Cannot insert event: {(racer_id, control_point, timestamp, user_id)}", exc_info=1)

    def get_events(self, min_lap):
        result = defaultdict(list)
        prev_id = None
        prev_ts = None
        with contextlib.closing(self.connect()) as ccon:
            with ccon as con:
                for row in con.execute(ALL_EVENTS).fetchall():
                    racer_id, kp_id, timestamp, _ = row
                    if validate(prev_id, prev_ts, racer_id, timestamp, min_lap):
                        result[racer_id].append(RacePoint(timestamp, kp_id))
                        prev_id = racer_id
                        prev_ts = timestamp
        return result
    
    def get_race_state(self):
        with contextlib.closing(self.connect()) as ccon:
            with ccon as con:
                return {row[0]:row[1] for row in con.execute(ALL_EVENTS).fetchall()} 
    
    def get_raw_events(self):
        with contextlib.closing(self.connect()) as ccon:
                with ccon as con:
                    for row in con.execute(ALL_EVENTS_RAW).fetchall():
                        racer_id, kp_id, timestamp, user = row
                        yield racer_id, kp_id, timestamp, user

    def get_kp_events(self, kp_id):
        with contextlib.closing(self.connect()) as ccon:
            with ccon as con:
                for row in con.execute(KPP_EVENTS, (kp_id,)):
                    racer_id,timestamp = row
                    yield KPPoint(timestamp,racer_id)
    
    def wipe(self):
        with contextlib.closing(self.connect()) as ccon:
            with ccon as con:
                con.execute(DELETE_ALL)

def validate(prev_id, prev_ts, racer_id, timestamp, min_lap):
    return (prev_id != racer_id) or (prev_ts is None) or (timestamp-prev_ts) >= min_lap 
