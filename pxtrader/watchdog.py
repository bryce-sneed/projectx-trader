"""
Process watchdog — subprocess supervision lessons from production incidents.

These patterns complement the in-process ``supervise`` loop: pause-before-spawn, fail-closed
process enumeration, and supervisor-first stop with verification.
"""
from __future__ import annotations

import time as _time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Protocol


class AccessDenied(Exception):
    """Process metadata could not be read (elevated / protected process)."""


class NoSuchProcess(Exception):
    """Process exited or was reaped between listing and inspection."""


class ZombieProcess(Exception):
    """Process is a zombie (reaped by kernel, not yet waited on by parent)."""


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str = ""
    cmdline: tuple[str, ...] = ()


class _ProcLike(Protocol):
    def info(self) -> ProcessInfo: ...


def count_matching_processes(
    predicate: Callable[[ProcessInfo], bool],
    processes: Iterable[_ProcLike],
    *,
    exclude_pid: Optional[int] = None,
) -> int:
    """Count processes matching ``predicate``.

    * ``AccessDenied`` → count as a match (fail closed: invisible ≠ absent).
    * ``NoSuchProcess`` / ``ZombieProcess`` → skip (dead ≠ present).
    * ``exclude_pid`` → never count the caller's own PID (avoids self-match on cmdline).
    """
    count = 0
    for proc in processes:
        try:
            info = proc.info()
        except NoSuchProcess:
            continue
        except ZombieProcess:
            continue
        except AccessDenied:
            count += 1
            continue
        if exclude_pid is not None and info.pid == exclude_pid:
            continue
        if predicate(info):
            count += 1
    return count


def spawn_if_not_paused(
    *,
    paused: Callable[[], bool],
    spawn: Callable[[], int],
    sleep: Callable[[float], None] = _time.sleep,
    within_window: Callable[[], bool],
    poll_seconds: float = 0.0,
) -> Optional[int]:
    """Wait for ``within_window``, then check ``paused`` immediately before spawn.

    The production bug: pause was checked only inside the ``while not within_window()`` loop, so a
    watchdog started mid-window spawned without ever reading the flag. The wait loop cannot honour
    pause on its own — both branches only sleep — the pre-spawn check is the real guard.
    """
    while not within_window():
        sleep(poll_seconds)
    if paused():
        return None
    return spawn()


@dataclass
class StopResult:
    success: bool
    remaining_pids: tuple[int, ...] = ()


def stop_supervised(
    supervisor_pid: int,
    child_pid: int,
    *,
    terminate: Callable[[int], None],
    list_alive: Callable[[], tuple[int, ...]],
) -> StopResult:
    """Stop supervisor first (so it cannot respawn), then the child, then verify both are gone."""
    terminate(supervisor_pid)
    terminate(child_pid)
    remaining = tuple(pid for pid in list_alive() if pid in (supervisor_pid, child_pid))
    return StopResult(success=len(remaining) == 0, remaining_pids=remaining)
