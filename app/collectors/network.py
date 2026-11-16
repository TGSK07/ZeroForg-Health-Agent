import psutil


def collect_network(rates, ts):
    """Sample per-interface bandwidth, drops, errors, plus TCP connection and listening-port info.

    Returns (rows, listening_ports). rows are (metric name, subject, value).
    """
    rows = []
    for nic, c in psutil.net_io_counters(pernic=True).items():
        if nic == "lo" or nic.lower().startswith("loopback"):
            continue
        counters = {
            "net_up_Bps": c.bytes_sent,
            "net_down_Bps": c.bytes_recv,
            "net_drops_ps": c.dropin + c.dropout,
            "net_errors_ps": c.errin + c.errout,
        }
        for name, value in counters.items():
            r = rates.rate((name, nic), value, ts)
            if r is not None:
                rows.append((name, nic, r))

    ports = []
    try:
        conns = psutil.net_connections(kind="tcp")
        rows.append(("tcp_established", "", sum(1 for c in conns if c.status == "ESTABLISHED")))
        ports = sorted({c.laddr.port for c in conns if c.status == "LISTEN"})
        rows.append(("listening_ports", "", len(ports)))
    except (psutil.AccessDenied, RuntimeError, OSError):
        pass
    return rows, ports
