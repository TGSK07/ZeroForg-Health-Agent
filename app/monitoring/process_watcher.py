from collections import deque

from app.alerts import rules
from app.config import settings


class ProcessWatcher:
    """Tracks watch-list exits, long-lived zombies and steadily growing memory."""

    def __init__(self, engine, watchlist):
        self.engine = engine
        self.watchlist = [w.lower() for w in watchlist]
        self.last_pid = {}        # watch name -> last PID seen running
        self.dead = {}            # watch name -> alert subject ("name pid=123") while it is missing
        self.zombie_since = {}    # pid -> first time seen as zombie
        self.rss = {}             # pid -> last 10 one-minute RSS samples (MB)
        self.rss_at = {}          # pid -> time of last RSS sample
        self.mem_state = {}       # pid -> (active, growth MB, detail) from the latest full window

    def update(self, ts, procs):
        """Process one snapshot. Returns {rule: {subject: (active, value, detail)}}."""
        alive = {p["pid"] for p in procs}
        return {
            "process_died": self._died(procs),
            "zombie": self._zombies(ts, procs),
            "mem_climbing": self._memory(ts, procs, alive),
        }

    def _died(self, procs):
        """A watch-list name that was running and is now gone (zombies don't count as running)."""
        for name in self.watchlist:
            running = [p for p in procs if p["status"] != "zombie"
                       and (p["name"].lower() == name or name in p["cmdline"].lower())]
            if running:
                self.last_pid[name] = running[0]["pid"]
                self.dead.pop(name, None)
            elif name in self.last_pid:
                self.dead.setdefault(name, f"{name} pid={self.last_pid[name]}")
        return {s: (True, 1, f"watched process '{n}' exited unexpectedly ({s})") for n, s in self.dead.items()}

    def _zombies(self, ts, procs):
        """Processes in state Z for more than ZOMBIE_SECONDS."""
        zombies = {p["pid"]: p for p in procs if p["status"] == "zombie"}
        self.zombie_since = {pid: self.zombie_since.get(pid, ts) for pid in zombies}
        states = {}
        for pid, p in zombies.items():
            age = ts - self.zombie_since[pid]
            states[f"{p['name']}:{pid}"] = (age > rules.ZOMBIE_SECONDS, age, f"zombie for {age:.0f}s")
        return states

    def _memory(self, ts, procs, alive):
        """Sample each process's RSS once per mem_sample_seconds and look for steady growth."""
        for pid in [p for p in self.rss if p not in alive]:
            for d in (self.rss, self.rss_at, self.mem_state):
                d.pop(pid, None)
        for p in procs:
            pid = p["pid"]
            if ts - self.rss_at.get(pid, 0) < settings.mem_sample_seconds - 2.5:
                continue
            self.rss_at[pid] = ts
            hist = self.rss.setdefault(pid, deque(maxlen=rules.MEM_WINDOW))
            hist.append(p["rss_mb"])
            if len(hist) < rules.MEM_WINDOW:
                continue
            h = list(hist)
            rises = sum(1 for a, b in zip(h, h[1:]) if b > a)
            growth = h[-1] - h[0]
            subject = f"{p['name']}:{pid}"
            if self.engine.is_open("mem_climbing", subject):
                active = growth >= rules.MEM_GROWTH_HOLD and rises >= rules.MEM_RISES_HOLD
            else:
                active = growth >= rules.MEM_GROWTH_FIRE and rises >= rules.MEM_RISES_FIRE
            self.mem_state[pid] = (subject, (active, growth,
                                             f"RSS {h[0]:.0f}->{h[-1]:.0f} MB, {rises}/9 rises (pid {pid})"))
        return {subject: state for subject, state in self.mem_state.values()}
