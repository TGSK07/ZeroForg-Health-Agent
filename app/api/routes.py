import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.alerts.rules import SEVERITY
from app.api.schemas import Alert, Health, MetricPoint, ProcessInfo
from app.db import repository as repo

router = APIRouter()

SORT_KEYS = {"cpu": "cpu", "ram": "rss_mb", "pid": "pid", "name": "name", "fds": "fds"}


def parse_since(value: Optional[str]) -> float:
    """'1h' / '30m' / '2d' (relative), a number of epoch seconds, or empty (= last hour)."""
    now = time.time()
    if not value:
        return now - 3600
    try:
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        if value[-1] in units:
            return now - float(value[:-1]) * units[value[-1]]
        return float(value)
    except ValueError:
        raise HTTPException(400, "since must look like 30m, 1h, 2d or epoch seconds")


@router.get("/health", response_model=Health)
def health(request: Request):
    """Overall status (ok / warn / critical) plus all open alerts."""
    open_alerts = repo.list_alerts(open_only=True)
    severities = {SEVERITY.get(a["rule"]) for a in open_alerts}
    status = "critical" if "critical" in severities else "warn" if open_alerts else "ok"
    return {"status": status, "checked_at": time.time(), "open_alerts": open_alerts,
            "listening_ports": request.app.state.agent.ports}


@router.get("/metrics", response_model=List[MetricPoint])
def metrics(name: str, since: Optional[str] = None, step: int = 0, subject: Optional[str] = None):
    """History of one metric. `step` (seconds) averages points into buckets for long ranges."""
    return repo.query_metrics(name, parse_since(since), step, subject)


@router.get("/alerts", response_model=List[Alert])
def alerts(open: Optional[bool] = None, limit: int = Query(200, le=1000)):
    """Alert history. open=true -> open only, open=false -> closed only, omitted -> all."""
    return repo.list_alerts(open_only=open, limit=limit)


@router.get("/processes", response_model=List[ProcessInfo])
def processes(request: Request, sort: str = "cpu", limit: int = Query(50, le=500)):
    """Latest process snapshot sorted by cpu, ram, pid, name or fds."""
    if sort not in SORT_KEYS:
        raise HTTPException(400, f"sort must be one of {sorted(SORT_KEYS)}")
    key = SORT_KEYS[sort]
    rows = request.app.state.agent.procs
    if key == "name":
        rows = sorted(rows, key=lambda p: p["name"].lower())
    elif key == "pid":
        rows = sorted(rows, key=lambda p: p["pid"])
    else:
        rows = sorted(rows, key=lambda p: p[key] or 0, reverse=True)
    return rows[:limit]
