import os
import time

import psutil

MB = 1024 * 1024
_self = psutil.Process(os.getpid())

# Filesystems worth watching (tmpfs included so a small test tmpfs mount is seen).
FS_TYPES = {"ext2", "ext3", "ext4", "xfs", "btrfs", "f2fs", "vfat", "ntfs", "tmpfs", "zfs", "apfs"}
SKIP_PREFIXES = ("/run", "/dev", "/sys", "/proc", "/snap", "/boot/efi")


class RateTracker:
    """Turns ever-growing counters into per-second rates.

    The first sample and any sample where the counter went backwards (reset / reboot /
    interface re-created) return None, so a reset never produces a negative or huge rate.
    """

    def __init__(self):
        self.prev = {}  # key -> (timestamp, counter value)

    def rate(self, key, value, ts):
        old = self.prev.get(key)
        self.prev[key] = (ts, value)
        if old is None:
            return None
        dt, delta = ts - old[0], value - old[1]
        if dt <= 0 or delta < 0:
            return None
        return delta / dt


def _mounts():
    """Mount points of real filesystems, skipping pseudo / system ones."""
    seen, out = set(), []
    for p in psutil.disk_partitions(all=True):
        if p.fstype.lower() not in FS_TYPES or p.mountpoint in seen:
            continue
        if p.mountpoint.startswith(SKIP_PREFIXES) or "cdrom" in p.opts:
            continue
        seen.add(p.mountpoint)
        out.append(p.mountpoint)
    return out


def collect_system(rates, ts):
    """Sample CPU, RAM, swap, disk usage, disk I/O rates, uptime, load and the agent's own usage.

    Returns a list of (metric name, subject, value).
    """
    rows = []
    cores = psutil.cpu_percent(percpu=True)
    for i, pct in enumerate(cores):
        rows.append(("cpu_core", f"core{i}", pct))
    rows.append(("cpu_total", "", psutil.cpu_percent()))

    vm = psutil.virtual_memory()
    rows.append(("ram_percent", "", vm.percent))
    rows.append(("ram_used_mb", "", (vm.total - vm.available) / MB))
    try:
        rows.append(("swap_percent", "", psutil.swap_memory().percent))
    except (RuntimeError, OSError):   # swap counters unavailable on some hosts
        pass

    for mount in _mounts():
        try:
            rows.append(("disk_percent", mount, psutil.disk_usage(mount).percent))
        except OSError:
            pass

    io = psutil.disk_io_counters()
    if io:
        for name, value in (("disk_read_Bps", io.read_bytes), ("disk_write_Bps", io.write_bytes)):
            r = rates.rate(name, value, ts)
            if r is not None:
                rows.append((name, "", r))

    rows.append(("uptime_s", "", time.time() - psutil.boot_time()))
    try:
        for label, value in zip(("load1", "load5", "load15"), psutil.getloadavg()):
            rows.append((label, "", value))
    except (RuntimeError, OSError):   # load average unavailable on some hosts
        pass

    # The agent's own footprint, to prove it stays inside its budget.
    rows.append(("agent_cpu_percent", "", _self.cpu_percent()))
    rows.append(("agent_rss_mb", "", _self.memory_info().rss / MB))
    return rows
