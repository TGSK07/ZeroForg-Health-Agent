from app.collectors.system import RateTracker


def test_rate_is_delta_over_time():
    r = RateTracker()
    assert r.rate("x", 100, 0) is None        # first sample has no rate
    assert r.rate("x", 600, 5) == 100         # 500 bytes in 5 s


def test_counter_reset_is_skipped():
    r = RateTracker()
    r.rate("x", 1000, 0)
    assert r.rate("x", 10, 5) is None         # counter went backwards -> no negative rate
    assert r.rate("x", 60, 10) == 10          # recovers on the next sample
