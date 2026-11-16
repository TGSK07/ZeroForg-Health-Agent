from app.alerts.engine import AlertEngine
from app.alerts.rules import Rules
from app.db import db, repository as repo


T0 = 1_700_000_000


def setup(tmp_path):
    """Fresh DB + engine + rules."""
    db.init_db(str(tmp_path / "t.db"))
    engine = AlertEngine()
    return engine, Rules(engine)


def test_cpu_needs_60s_and_no_flapping(tmp_path):
    engine, rules = setup(tmp_path)
    for t in range(T0, T0 + 60, 5):                       # 0..55 s: not yet
        rules.check_system(t, [("cpu_total", "", 95)])
        assert not engine.is_open("cpu_high", "total")
    rules.check_system(T0 + 60, [("cpu_total", "", 95)])  # 60 s: opens
    assert engine.is_open("cpu_high", "total")
    rules.check_system(T0 + 65, [("cpu_total", "", 82)])  # between clear (80) and fire (85): stays open
    assert engine.is_open("cpu_high", "total")
    rules.check_system(T0 + 70, [("cpu_total", "", 50)])  # clears
    assert not engine.is_open("cpu_high", "total")
    assert len(repo.list_alerts()) == 1


def test_cpu_dip_resets_timer(tmp_path):
    engine, rules = setup(tmp_path)
    for t in range(T0, T0 + 50, 5):
        rules.check_system(t, [("cpu_total", "", 95)])
    rules.check_system(T0 + 50, [("cpu_total", "", 10)])
    for t in range(T0 + 55, T0 + 110, 5):
        rules.check_system(t, [("cpu_total", "", 95)])
    assert not engine.is_open("cpu_high", "total")


def test_network_lost_after_3_fails_and_closes(tmp_path):
    engine, rules = setup(tmp_path)
    for t in (T0, T0 + 15):
        rules.check_network(t, {"gateway": True, "internet": False})
    assert not engine.is_open("network_lost", "gateway")
    rules.check_network(T0 + 30, {"gateway": True, "internet": False})
    assert engine.is_open("network_lost", "gateway")
    rules.check_network(T0 + 45, {"gateway": False, "internet": False})
    assert not engine.is_open("network_lost", "gateway")
