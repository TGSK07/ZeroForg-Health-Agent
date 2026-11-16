import re
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# Worker threads so that a hung lookup/connect can never block the caller.
_pool = ThreadPoolExecutor(max_workers=16)
_WIN = sys.platform.startswith("win")


def _wait(future, timeout):
    """Result of a future, or None if it failed or took longer than `timeout`."""
    try:
        return future.result(timeout=timeout)
    except Exception:
        return None


def dns_time(host, timeout):
    """Resolve `host`; returns (milliseconds, ip) or None on failure. Runs under a hard timeout."""
    def work():
        t = time.perf_counter()
        ip = socket.getaddrinfo(host, None, socket.AF_INET)[0][4][0]
        return (time.perf_counter() - t) * 1000, ip
    return _wait(_pool.submit(work), timeout)


def tcp_time(ip, port, timeout):
    """Time a TCP connect to ip:port in milliseconds, or None on failure."""
    t = time.perf_counter()
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return (time.perf_counter() - t) * 1000
    except OSError:
        return None


def ping_loss(host, timeout, count=3):
    """Send `count` pings and return packet loss % (None if ping is unavailable).

    Replies are counted by the 'ttl=' marker, which works regardless of OS language.
    """
    if _WIN:
        cmd = ["ping", "-n", str(count), "-w", str(int(timeout * 1000)), host]
    else:
        cmd = ["ping", "-c", str(count), "-i", "0.3", "-W", str(max(1, int(timeout))), host]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=count * (timeout + 1) + 2).stdout
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return 100.0
    received = out.lower().count("ttl=")
    return max(0.0, (count - received) / count * 100)


def default_gateway(configured=""):
    """Default gateway IP: from config, /proc/net/route (Linux) or ipconfig (Windows). '' if none."""
    if configured:
        return configured
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                p = line.split()
                if p[1] == "00000000" and int(p[3], 16) & 2:
                    return socket.inet_ntoa(struct.pack("<L", int(p[2], 16)))
    except OSError:
        pass
    if _WIN:
        try:
            out = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"Default Gateway[ .]*:\s*(\d+\.\d+\.\d+\.\d+)", out)
            return m.group(1) if m else ""
        except Exception:
            pass
    return ""


def api_probe(url, timeout):
    """GET `url`; returns (milliseconds, HTTP status) or None if unreachable / timed out."""
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception:
        return None
    return (time.perf_counter() - t) * 1000, status


def run_probes(cfg):
    """Run all network probes in parallel, each with a timeout.

    Returns (rows, failed): rows are (name, subject, value) metrics; failed is
    {"gateway": bool, "internet": bool} for the network-lost rule. A failed latency probe
    stores no latency row (leaving a visible gap) but does store *_ok = 0.
    """
    t = cfg.probe_timeout
    gw = default_gateway(cfg.gateway)
    f_dns = _pool.submit(dns_time, cfg.dns_host, t)
    f_gw = _pool.submit(ping_loss, gw, t) if gw else None
    f_net = _pool.submit(ping_loss, cfg.internet_host, t)
    f_api = _pool.submit(api_probe, cfg.api_url, t)

    rows = []
    dns = _wait(f_dns, t + 1)
    rows.append(("dns_ok", "", 1 if dns else 0))
    tcp = None
    if dns:
        rows.append(("dns_ms", "", dns[0]))
        tcp = _wait(_pool.submit(tcp_time, dns[1], cfg.tcp_port, t), t + 1)
    rows.append(("tcp_ok", "", 1 if tcp is not None else 0))
    if tcp is not None:
        rows.append(("tcp_ms", "", tcp))

    # No gateway at all (cable out, no route) counts as the gateway not answering.
    gw_loss = _wait(f_gw, 3 * (t + 1) + 3) if f_gw else 100.0
    net_loss = _wait(f_net, 3 * (t + 1) + 3)
    for name, loss in (("gateway_loss", gw_loss), ("internet_loss", net_loss)):
        if loss is not None:
            rows.append((name, "", loss))

    api = _wait(f_api, t + 1)
    rows.append(("api_ok", "", 1 if api else 0))
    rows.append(("api_status", "", api[1] if api else 0))
    if api:
        rows.append(("api_ms", "", api[0]))

    failed = {"gateway": gw_loss == 100.0, "internet": net_loss == 100.0}
    return rows, failed
