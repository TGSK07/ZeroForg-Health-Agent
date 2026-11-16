import logging
import threading
import time

from app.alerts.engine import AlertEngine
from app.alerts.rules import Rules
from app.collectors.network import collect_network
from app.collectors.processes import collect_processes
from app.collectors.system import RateTracker, collect_system
from app.config import settings
from app.db import db, repository as repo
from app.monitoring.probes import run_probes
from app.monitoring.process_watcher import ProcessWatcher

log = logging.getLogger("zeroforg")


class Agent:
    """Runs the sampler (every 5 s) and the network prober (every 15 s) in background threads."""

    def __init__(self):
        self.stop_event = threading.Event()
        self.threads = []
        self.procs = []          # latest process snapshot, served by /processes
        self.ports = []          # latest listening ports
        self.rates = RateTracker()
        self.last_prune = 0

    def start(self):
        """Open the DB, prime the CPU/rate counters, and launch the worker threads."""
        db.init_db(settings.db_path)
        self.engine = AlertEngine()
        self.rules = Rules(self.engine)
        self.watcher = ProcessWatcher(self.engine, settings.watchlist)
        self.sample_once(store=False)   # first reading of CPU % / rates is meaningless
        for target, interval in ((self.sample_once, settings.sample_interval),
                                 (self.probe_once, settings.probe_interval)):
            t = threading.Thread(target=self._loop, args=(target, interval), daemon=True)
            t.start()
            self.threads.append(t)

    def stop(self):
        """Ask the worker threads to exit."""
        self.stop_event.set()

    def _loop(self, fn, interval):
        """Call fn every `interval` seconds on a fixed schedule (no drift); errors never kill the loop."""
        next_run = time.monotonic() + interval
        while not self.stop_event.wait(max(0, next_run - time.monotonic())):
            next_run += interval
            try:
                fn()
            except Exception:
                log.exception("%s failed", fn.__name__)

    def sample_once(self, store=True):
        """Collect system, network and process metrics, store them, then evaluate rules."""
        ts = time.time()
        rows = collect_system(self.rates, ts)
        net_rows, self.ports = collect_network(self.rates, ts)
        rows += net_rows
        procs = collect_processes()
        rows.append(("process_count", "", len(procs)))
        if not store:
            return
        self.procs = procs
        repo.insert_metrics(ts, rows)
        self.rules.check_system(ts, rows)
        for rule, states in self.watcher.update(ts, procs).items():
            self.engine.sync(rule, states, ts)
        if ts - self.last_prune > 3600:
            repo.prune(settings.retention_days)
            self.last_prune = ts

    def probe_once(self):
        """Run the network probes, store results and evaluate the network-lost rule."""
        rows, failed = run_probes(settings)
        ts = time.time()
        repo.insert_metrics(ts, rows)
        self.rules.check_network(ts, failed)
