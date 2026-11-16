import sqlite3
import threading

from app.config import settings
from app.db.models import SCHEMA

lock = threading.RLock()   # one connection shared by sampler, prober and API threads
_conn = None


def init_db(path=None):
    """Open (or create) the SQLite file in WAL mode and make sure the tables exist."""
    global _conn
    with lock:
        if _conn is not None:
            _conn.close()
        _conn = sqlite3.connect(path or settings.db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def get_conn():
    """Return the shared connection, opening it on first use."""
    return _conn if _conn is not None else init_db()
