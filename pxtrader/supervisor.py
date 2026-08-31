"""
Supervisor — keep a live run loop alive, and stop it cleanly on demand.

``supervise`` runs a function (typically a ``run_live`` call); if it crashes it restarts it, up to
``max_restarts`` within a rolling window, with backoff — then gives up and asks for a human rather
than crash-looping forever. A file-based ``KillSwitch`` lets you halt from anywhere (create the
file) and is honored both between restarts and, via ``should_stop``, inside the run loop.

    from pxtrader.supervisor import supervise, KillSwitch
    ks = KillSwitch("HALT")          # `touch HALT` to stop the bot
    supervise(lambda should_stop: run_live(client, strat, symbol="MNQ", symbol_id="F.US.MNQ",
                                            should_stop=should_stop),
              kill_switch=ks)
"""
from __future__ import annotations

import time as _time
import traceback
from pathlib import Path
from typing import Callable, List, Optional


class KillSwitch:
    """File-based stop flag. Create the file to halt; delete it to allow running again.

    Scoped to **live** execution by default. A halt file must never silence backtest replay —
    the production bug checked it unconditionally and reported "no trades" as if that were a result.
    """

    def __init__(self, path: str):
        self.path = Path(path)

    def engaged(self, *, execution: str = "live") -> bool:
        """True when the halt file exists and applies to ``execution`` (``"live"`` or ``"backtest"``)."""
        if not self.path.exists():
            return False
        if execution == "backtest":
            return False
        return True

    def engage(self) -> None:
        self.path.write_text("halt\n", encoding="utf-8")

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


def supervise(run_fn: Callable[..., None], *, max_restarts: int = 10, window_seconds: float = 600,
              backoff_seconds: float = 5.0, kill_switch: Optional[KillSwitch] = None,
              logger: Optional[Callable[[str], None]] = None) -> None:
    """Run ``run_fn(should_stop=...)``; restart it on crash within limits; stop on the kill-switch.

    ``run_fn`` should accept a ``should_stop`` callable and return when it reports True (a clean
    stop). Any exception that escapes ``run_fn`` is treated as a crash and triggers a restart.
    """
    log = logger or (lambda m: print(f"[supervisor] {m}"))

    def should_stop() -> bool:
        return bool(kill_switch and kill_switch.engaged(execution="live"))

    restarts: List[float] = []
    while True:
        if should_stop():
            log("kill-switch engaged -> not starting")
            return
        try:
            run_fn(should_stop=should_stop)
            log("run loop returned cleanly -> stopping")
            return
        except Exception as e:
            log(f"run loop CRASHED: {e}")
            log(traceback.format_exc().strip().splitlines()[-1])

        now = _time.time()
        restarts = [t for t in restarts if now - t < window_seconds]
        if len(restarts) >= max_restarts:
            log(f"{max_restarts} restarts within {int(window_seconds)}s -> giving up (human needed)")
            return
        restarts.append(now)
        if should_stop():
            log("kill-switch engaged during backoff -> stopping")
            return
        log(f"restarting in {backoff_seconds:.0f}s ({len(restarts)}/{max_restarts})")
        _time.sleep(backoff_seconds)
