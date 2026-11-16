from typing import List, Optional

from pydantic import BaseModel


class Alert(BaseModel):
    id: int
    rule: str
    subject: str
    severity: str
    opened_at: float
    closed_at: Optional[float] = None
    peak: Optional[float] = None
    detail: Optional[str] = None
    opened_at_iso: Optional[str] = None
    closed_at_iso: Optional[str] = None


class Health(BaseModel):
    status: str                 # ok | warn | critical
    checked_at: float
    open_alerts: List[Alert]
    listening_ports: List[int]


class MetricPoint(BaseModel):
    ts: float
    subject: str
    value: float


class ProcessInfo(BaseModel):
    pid: int
    name: str
    cmdline: str
    status: str
    cpu: float
    rss_mb: float
    fds: Optional[int] = None
    flags: List[str]
