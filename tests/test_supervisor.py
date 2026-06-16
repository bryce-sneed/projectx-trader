"""
Supervisor tests — clean return, crash-restart, give-up cap, and the kill-switch. No sleeps.

    pytest tests/test_supervisor.py -v
"""
from pxtrader.supervisor import KillSwitch, supervise

_QUIET = lambda m: None


def test_clean_return_runs_once():
    calls = {"n": 0}
    supervise(lambda should_stop: calls.__setitem__("n", calls["n"] + 1),
              backoff_seconds=0, logger=_QUIET)
    assert calls["n"] == 1


def test_restarts_then_succeeds():
    calls = {"n": 0}

    def run(should_stop):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")

    supervise(run, backoff_seconds=0, max_restarts=10, logger=_QUIET)
    assert calls["n"] == 3


def test_gives_up_after_max_restarts():
    calls = {"n": 0}

    def run(should_stop):
        calls["n"] += 1
        raise RuntimeError("always crashes")

    supervise(run, backoff_seconds=0, max_restarts=3, logger=_QUIET)
    assert calls["n"] == 4          # max_restarts + 1 attempts, then gives up


def test_killswitch_prevents_start(tmp_path):
    ks = KillSwitch(str(tmp_path / "HALT"))
    ks.engage()
    calls = {"n": 0}
    supervise(lambda should_stop: calls.__setitem__("n", calls["n"] + 1),
              kill_switch=ks, backoff_seconds=0, logger=_QUIET)
    assert calls["n"] == 0


def test_killswitch_stops_after_crash(tmp_path):
    ks = KillSwitch(str(tmp_path / "HALT"))
    calls = {"n": 0}

    def run(should_stop):
        calls["n"] += 1
        ks.engage()                 # halt requested mid-run
        raise RuntimeError("boom")

    supervise(run, kill_switch=ks, backoff_seconds=0, logger=_QUIET)
    assert calls["n"] == 1          # crashed once; kill-switch -> no restart


def test_killswitch_file_lifecycle(tmp_path):
    ks = KillSwitch(str(tmp_path / "HALT"))
    assert not ks.engaged()
    ks.engage()
    assert ks.engaged()
    ks.clear()
    assert not ks.engaged()
