import json
import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    """All tunables with defaults; any key can be overridden in config.json."""
    app_name: str = "ZeroForg Health Agent"
    db_path: str = "zeroforg.db"
    sample_interval: int = 5          # seconds between system/process samples
    probe_interval: int = 15          # seconds between network probes
    probe_timeout: float = 3.0        # per-probe timeout (seconds)
    retention_days: int = 7           # history kept in SQLite
    mem_sample_seconds: int = 60      # spacing of per-process RSS samples (memory-climbing rule)
    watchlist: list = field(default_factory=list)  # process names that must stay alive
    dns_host: str = "example.com"     # host for DNS + TCP connect probes
    tcp_port: int = 443
    internet_host: str = "1.1.1.1"    # host for packet-loss probe
    gateway: str = ""                 # empty = auto-detect default gateway
    api_url: str = "https://example.com"


def load_settings() -> Settings:
    """Build Settings from defaults, then config.json (ZEROFORG_CONFIG), then ZEROFORG_DB env."""
    s = Settings()
    path = os.getenv("ZEROFORG_CONFIG", "config.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for key, value in json.load(f).items():
                if hasattr(s, key):
                    setattr(s, key, value)
    s.db_path = os.getenv("ZEROFORG_DB", s.db_path)
    return s


settings = load_settings()
