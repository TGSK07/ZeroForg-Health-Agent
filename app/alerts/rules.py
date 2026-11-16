"""Alert rules. Thresholds are constants; each rule has a lower 'clear' level to avoid flapping."""

SEVERITY = {
    "cpu_high": "warn",
    "ram_high": "critical",
    "disk_high": "critical",
    "network_lost": "critical",
    "mem_climbing": "warn",
    "process_died": "critical",
    "zombie": "warn",
}

CPU_FIRE, CPU_CLEAR, CPU_SECONDS = 85, 80, 60      # total CPU % must stay > 85 for 60 s; clears < 80
RAM_FIRE, RAM_CLEAR = 90, 87                       # RAM %; clears below 87
DISK_FIRE, DISK_CLEAR = 90, 87                     # per mount; clears below 87
NET_FAILS = 3                                      # consecutive failed probes
ZOMBIE_SECONDS = 30                                # Z state longer than this
# Memory climbing: 10 one-minute RSS samples (9 intervals). Fires if >= 8 of 9 intervals rose and
# total growth >= 50 MB. Stays open while growth >= 10 MB and >= 5 intervals rose.
MEM_WINDOW, MEM_RISES_FIRE, MEM_GROWTH_FIRE = 10, 8, 50
MEM_RISES_HOLD, MEM_GROWTH_HOLD = 5, 10


class Rules:
    """Evaluates system and network rules and pushes results into the AlertEngine."""

    def __init__(self, engine):
        self.engine = engine
        self.cpu_since = None      # when CPU first went above CPU_FIRE in the current unbroken run
        self.net_fails = {}        # probe target -> consecutive failures

    def check_system(self, ts, rows):
        """Evaluate CPU, RAM and disk rules from one sample's (name, subject, value) rows."""
        m = {}
        for name, subject, value in rows:
            m.setdefault(name, {})[subject] = value
        eng = self.engine

        cpu = m.get("cpu_total", {}).get("")
        if cpu is not None:
            is_open = eng.is_open("cpu_high", "total")
            if cpu > CPU_FIRE:
                if self.cpu_since is None:
                    self.cpu_since = ts
            else:
                self.cpu_since = None          # a single dip below the line breaks the run
            if is_open:
                active = cpu > CPU_CLEAR
            else:
                active = self.cpu_since is not None and ts - self.cpu_since >= CPU_SECONDS
            eng.sync("cpu_high", {"total": (active, cpu, f"CPU {cpu:.0f}% for {CPU_SECONDS}s+")}, ts)

        ram = m.get("ram_percent", {}).get("")
        if ram is not None:
            limit = RAM_CLEAR if eng.is_open("ram_high", "ram") else RAM_FIRE
            eng.sync("ram_high", {"ram": (ram > limit, ram, f"RAM {ram:.0f}% used")}, ts)

        disks = m.get("disk_percent", {})
        states = {}
        for mount, pct in disks.items():
            limit = DISK_CLEAR if eng.is_open("disk_high", mount) else DISK_FIRE
            states[mount] = (pct > limit, pct, f"{mount} {pct:.0f}% used")
        eng.sync("disk_high", states, ts)

    def check_network(self, ts, failed):
        """failed: {"gateway": bool, "internet": bool} for this probe round."""
        states = {}
        for target, did_fail in failed.items():
            count = self.net_fails.get(target, 0) + 1 if did_fail else 0
            self.net_fails[target] = count
            states[target] = (count >= NET_FAILS, count, f"{target} unreachable ({count} probes in a row)")
        self.engine.sync("network_lost", states, ts)
