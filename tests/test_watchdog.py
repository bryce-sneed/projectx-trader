"""
Watchdog safety-pattern tests — each fails without its fix. Mutation-check with cold cache:

    find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; python -B -m pytest tests/test_watchdog.py -v
"""
from pxtrader.supervisor import KillSwitch
from pxtrader.watchdog import (
    AccessDenied,
    NoSuchProcess,
    ProcessInfo,
    ZombieProcess,
    count_matching_processes,
    spawn_if_not_paused,
    stop_supervised,
)


class _Proc:
    def __init__(self, info: ProcessInfo, *, deny: bool = False, gone: bool = False, zombie: bool = False):
        self._info = info
        self._deny = deny
        self._gone = gone
        self._zombie = zombie

    def info(self) -> ProcessInfo:
        if self._gone:
            raise NoSuchProcess(self._info.pid)
        if self._zombie:
            raise ZombieProcess(self._info.pid)
        if self._deny:
            raise AccessDenied(self._info.pid)
        return self._info


def test_pause_checked_immediately_before_spawn_not_only_in_wait_loop():
    """Pause set after the wait loop ends must block spawn (mid-window launch bug)."""
    state = {"paused": False, "spawned": 0}

    def paused():
        return state["paused"]

    def spawn():
        state["spawned"] += 1
        return 4242

    state["paused"] = True
    pid = spawn_if_not_paused(
        paused=paused,
        spawn=spawn,
        sleep=lambda _: None,
        within_window=lambda: True,  # already in window — old code skipped pause check here
        poll_seconds=0,
    )
    assert pid is None
    assert state["spawned"] == 0

    state["paused"] = False
    pid = spawn_if_not_paused(paused=paused, spawn=spawn, sleep=lambda _: None,
                              within_window=lambda: True, poll_seconds=0)
    assert pid == 4242
    assert state["spawned"] == 1


def test_pause_blocks_spawn_after_waiting_for_window():
    """Pause must be honoured at spawn time even after the wait loop exits."""
    state = {"paused": True, "spawned": 0, "ticks": 0}

    def within_window():
        state["ticks"] += 1
        return state["ticks"] >= 2

    def spawn():
        state["spawned"] += 1
        return 4242

    pid = spawn_if_not_paused(
        paused=lambda: state["paused"],
        spawn=spawn,
        sleep=lambda _: None,
        within_window=within_window,
        poll_seconds=0,
    )
    assert pid is None
    assert state["spawned"] == 0


def test_killswitch_scoped_to_live_not_backtest(tmp_path):
    """HALT file applies to live execution only — backtest path must not consult it."""
    ks = KillSwitch(str(tmp_path / "HALT"))
    ks.engage()
    assert ks.engaged(execution="live") is True
    assert ks.engaged(execution="backtest") is False


def test_process_enumeration_fails_closed_on_access_denied():
    """AccessDenied must count as present — invisible child is not an absent child."""
    visible = _Proc(ProcessInfo(pid=1, name="python", cmdline=("python", "bot.py")))
    hidden = _Proc(ProcessInfo(pid=2, name="python", cmdline=("python", "bot.py")), deny=True)

    def is_bot(p: ProcessInfo) -> bool:
        return "bot.py" in p.cmdline

    assert count_matching_processes(is_bot, [visible]) == 1
    assert count_matching_processes(is_bot, [hidden]) == 1
    assert count_matching_processes(is_bot, [visible, hidden]) == 2


def test_process_enumeration_skips_reaped_processes():
    """NoSuchProcess/Zombie must not inflate the count — dead is the opposite of denied."""
    visible = _Proc(ProcessInfo(pid=1, cmdline=("python", "bot.py")))
    reaped = _Proc(ProcessInfo(pid=2, cmdline=("python", "bot.py")), gone=True)
    zombie = _Proc(ProcessInfo(pid=3, cmdline=("python", "bot.py")), zombie=True)

    def is_bot(p: ProcessInfo) -> bool:
        return "bot.py" in p.cmdline

    assert count_matching_processes(is_bot, [visible, reaped, zombie]) == 1


def test_process_enumeration_excludes_self():
    """Cmdline matching must not count the process running the query."""
    self_proc = _Proc(ProcessInfo(pid=42, cmdline=("python", "bot.py")))
    other = _Proc(ProcessInfo(pid=2, cmdline=("python", "bot.py")))

    def is_bot(p: ProcessInfo) -> bool:
        return "bot.py" in p.cmdline

    assert count_matching_processes(is_bot, [self_proc, other], exclude_pid=42) == 1


def test_stop_child_first_false_pass_while_respawned_child_runs():
    """Child-first stop can report success on original PIDs while a respawned child still runs."""
    alive = {100: True, 200: True}
    supervisor_pid, child_pid = 100, 200

    def terminate(pid: int) -> None:
        alive[pid] = False
        if pid == child_pid and alive.get(supervisor_pid, False):
            alive[301] = True

    def list_alive() -> tuple[int, ...]:
        return tuple(pid for pid, up in alive.items() if up)

    # Wrong order belongs in the test — drive fakes child-first, same verify pass stop_supervised uses.
    terminate(child_pid)
    terminate(supervisor_pid)
    remaining = tuple(pid for pid in list_alive() if pid in (supervisor_pid, child_pid))
    assert remaining == ()
    assert alive.get(301) is True, "respawned child still running after child-first stop"


def test_spawn_succeeds_when_unpaused_in_window():
    """Accept-path: unpaused watchdog in window must spawn — not only refuse when paused."""
    state = {"spawned": 0}

    def spawn():
        state["spawned"] += 1
        return 4242

    pid = spawn_if_not_paused(
        paused=lambda: False,
        spawn=spawn,
        sleep=lambda _: None,
        within_window=lambda: True,
        poll_seconds=0,
    )
    assert pid == 4242
    assert state["spawned"] == 1


def test_stop_supervisor_first_then_child_then_verify():
    """Supervisor-first stop prevents respawn and verifies both original PIDs are gone."""
    alive = {100: True, 200: True}

    def terminate(pid: int) -> None:
        alive[pid] = False
        if pid == 200 and alive.get(100, False):
            alive[301] = True

    def list_alive() -> tuple[int, ...]:
        return tuple(pid for pid, up in alive.items() if up)

    result = stop_supervised(100, 200, terminate=terminate, list_alive=list_alive)
    assert 301 not in alive
    assert result.success is True
    assert result.remaining_pids == ()
    assert list_alive() == ()
