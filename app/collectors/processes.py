import psutil

MB = 1024 * 1024
PROC_CPU_HIGH = 80        # % of one core
PROC_RAM_HIGH = 25        # % of total RAM

_FD_ATTR = "num_fds" if hasattr(psutil.Process, "num_fds") else "num_handles"
_ATTRS = ["pid", "name", "status", "cpu_percent", "memory_info", "cmdline", _FD_ATTR]


def collect_processes():
    """Snapshot every process: CPU %, RSS, open file descriptors, state and warning flags.

    psutil.process_iter reuses Process objects between calls, so cpu_percent is measured
    since the previous snapshot.
    """
    total = psutil.virtual_memory().total
    out = []
    for p in psutil.process_iter():
        try:
            i = p.as_dict(attrs=_ATTRS)
        except psutil.Error:
            continue
        mem = i["memory_info"]
        rss = mem.rss if mem else 0
        cpu = i["cpu_percent"] or 0.0
        flags = []
        if cpu > PROC_CPU_HIGH:
            flags.append("cpu_high")
        if rss / total * 100 > PROC_RAM_HIGH:
            flags.append("ram_high")
        if i["status"] == psutil.STATUS_ZOMBIE:
            flags.append("zombie")
        out.append({
            "pid": i["pid"],
            "name": i["name"] or "?",
            "cmdline": " ".join(i["cmdline"] or [])[:200],
            "status": i["status"],
            "cpu": round(cpu, 1),
            "rss_mb": round(rss / MB, 1),
            "fds": i[_FD_ATTR],
            "flags": flags,
        })
    return out
