"""SQLite schema. Timestamps are epoch seconds (UTC)."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
    ts      REAL NOT NULL,
    name    TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    value   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_name_ts ON metrics(name, ts);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts);

CREATE TABLE IF NOT EXISTS alerts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    rule      TEXT NOT NULL,
    subject   TEXT NOT NULL,
    severity  TEXT NOT NULL,
    opened_at REAL NOT NULL,
    closed_at REAL,
    peak      REAL,
    detail    TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_closed ON alerts(closed_at);
"""
