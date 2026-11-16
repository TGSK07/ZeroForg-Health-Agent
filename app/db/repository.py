import time
from datetime import datetime

from app.db import db


def _iso(ts):
    """Epoch seconds -> local ISO-8601 string (or None)."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _fetch(sql, args=()):
    """Run a SELECT and return rows as dicts."""
    with db.lock:
        return [dict(r) for r in db.get_conn().execute(sql, args).fetchall()]


def insert_metrics(ts, rows):
    """Store one sample: rows are (name, subject, value) tuples."""
    with db.lock:
        conn = db.get_conn()
        conn.executemany(
            "INSERT INTO metrics (ts, name, subject, value) VALUES (?,?,?,?)",
            [(ts, n, s, v) for n, s, v in rows],
        )
        conn.commit()


def query_metrics(name, since, step=0, subject=None, limit=50000):
    """Return points for one metric since `since`; step>0 averages into step-second buckets."""
    where, args = "name=? AND ts>=?", [name, since]
    if subject is not None:
        where += " AND subject=?"
        args.append(subject)
    if step and step > 0:
        sql = (f"SELECT CAST(ts/{int(step)} AS INTEGER)*{int(step)} AS ts, subject, AVG(value) AS value "
               f"FROM metrics WHERE {where} GROUP BY 1, subject ORDER BY 1 LIMIT ?")
    else:
        sql = f"SELECT ts, subject, value FROM metrics WHERE {where} ORDER BY ts LIMIT ?"
    return _fetch(sql, args + [limit])


def open_alert(rule, subject, severity, ts, value, detail):
    """Insert a new open alert and return its id."""
    with db.lock:
        conn = db.get_conn()
        cur = conn.execute(
            "INSERT INTO alerts (rule, subject, severity, opened_at, peak, detail) VALUES (?,?,?,?,?,?)",
            (rule, subject, severity, ts, value, detail))
        conn.commit()
        return cur.lastrowid


def update_peak(alert_id, value):
    """Record a new peak value for an open alert."""
    with db.lock:
        db.get_conn().execute("UPDATE alerts SET peak=? WHERE id=?", (value, alert_id))
        db.get_conn().commit()


def close_alert(alert_id, ts):
    """Mark an alert as closed."""
    with db.lock:
        db.get_conn().execute("UPDATE alerts SET closed_at=? WHERE id=?", (ts, alert_id))
        db.get_conn().commit()


def load_open_alerts():
    """All alerts that are still open (used to restore engine state after a restart)."""
    return _fetch("SELECT * FROM alerts WHERE closed_at IS NULL")


def list_alerts(open_only=None, limit=200):
    """Alerts newest first. open_only: True=open, False=closed, None=all."""
    sql = "SELECT * FROM alerts"
    if open_only is True:
        sql += " WHERE closed_at IS NULL"
    elif open_only is False:
        sql += " WHERE closed_at IS NOT NULL"
    rows = _fetch(sql + " ORDER BY opened_at DESC LIMIT ?", (limit,))
    for r in rows:
        r["opened_at_iso"] = _iso(r["opened_at"])
        r["closed_at_iso"] = _iso(r["closed_at"])
    return rows


def prune(retention_days):
    """Delete metrics and closed alerts older than the retention window (keeps the DB bounded)."""
    cutoff = time.time() - retention_days * 86400
    with db.lock:
        conn = db.get_conn()
        conn.execute("DELETE FROM metrics WHERE ts < ?", (cutoff,))
        conn.execute("DELETE FROM alerts WHERE closed_at IS NOT NULL AND closed_at < ?", (cutoff,))
        conn.commit()
