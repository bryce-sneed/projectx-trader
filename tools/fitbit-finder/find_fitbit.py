#!/usr/bin/env python3
"""Hot/cold Bluetooth finder for a lost Fitbit.

Run it on a laptop, then walk around: the signal bar grows as you get closer.

    pip install bleak
    python find_fitbit.py              # scan: list nearby devices, likely Fitbits first
    python find_fitbit.py --lock "Fitbit Air"  # live hot/cold meter
    python find_fitbit.py --survey "Fitbit Air"  # measure spot by spot, rank them

Before you start, turn Bluetooth OFF on the phone the Fitbit is paired with.
A tracker that is connected to its phone usually stops advertising, so nothing
else can see it.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time

from bleak import BleakScanner

# Fitbit's custom GATT service, advertised by most Fitbit trackers.
FITBIT_SERVICE = "adabfb00-6e7d-4601-bda2-bffaa68956ba"
# Bluetooth SIG company IDs: Fitbit, Google.
FITBIT_COMPANY_IDS = {0x0204: "Fitbit", 0x00E0: "Google"}
NAME_HINTS = ("fitbit", "air", "charge", "inspire", "luxe", "versa", "sense", "ace")


def fitbit_score(name: str | None, service_uuids, manufacturer_ids) -> int:
    """How likely an advertisement is a Fitbit: 0 = no evidence, higher = stronger."""
    score = 0
    if FITBIT_SERVICE in {u.lower() for u in service_uuids}:
        score += 3
    if 0x0204 in manufacturer_ids:
        score += 2
    elif 0x00E0 in manufacturer_ids:
        score += 1
    if name and any(h in name.lower() for h in NAME_HINTS):
        score += 2
    return score


def proximity(rssi: float) -> tuple[str, int]:
    """Map smoothed RSSI (dBm) to a label and a 0-40 bar length."""
    bar = max(0, min(40, int((rssi + 100) * 40 / 60)))  # -100 dBm -> 0, -40 dBm -> 40
    if rssi >= -50:
        label = "RIGHT HERE - look within ~1 m"
    elif rssi >= -62:
        label = "HOT - very close"
    elif rssi >= -72:
        label = "WARM - same room"
    elif rssi >= -84:
        label = "COOL - nearby"
    else:
        label = "COLD - far away"
    return label, bar


class Smoother:
    """Exponential moving average; raw BLE RSSI jumps around by +/-10 dB."""

    def __init__(self, alpha: float = 0.25):
        self.alpha = alpha
        self.value: float | None = None

    def add(self, x: float) -> float:
        self.value = x if self.value is None else self.alpha * x + (1 - self.alpha) * self.value
        return self.value


async def scan(seconds: float, show_all: bool) -> None:
    seen: dict[str, tuple] = {}

    def on_adv(device, adv):
        score = fitbit_score(adv.local_name or device.name, adv.service_uuids, adv.manufacturer_data.keys())
        seen[device.address] = (score, adv.rssi, adv.local_name or device.name or "(no name)", adv.manufacturer_data.keys())

    print(f"Scanning for {seconds:.0f}s... (phone Bluetooth off?)")
    async with BleakScanner(detection_callback=on_adv):
        await asyncio.sleep(seconds)

    rows = sorted(seen.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))
    if not show_all:
        rows = [r for r in rows if r[1][0] > 0] or rows
    print(f"\n{'likely':>6}  {'rssi':>5}  {'address':<40} name / maker")
    for addr, (score, rssi, name, mids) in rows:
        makers = ",".join(FITBIT_COMPANY_IDS.get(m, f"0x{m:04X}") for m in mids)
        print(f"{'*' * score:>6}  {rssi:>5}  {addr:<40} {name} {makers}")
    print('\nPick the best candidate and run:  python find_fitbit.py --lock "<name>"  (or the address)')
    print("Unsure which it is? Stand next to each candidate spot; the right one gets stronger.")


def is_address(s: str) -> bool:
    """MAC address (Windows/Linux) or UUID (macOS)."""
    return bool(re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}|[0-9a-f-]{36}", s.lower()))


async def lock(target: str) -> None:
    # Fitbits rotate their Bluetooth address every few minutes for privacy, so
    # matching by name (e.g. "Fitbit Air") keeps tracking after a rotation.
    by_address = is_address(target)
    target_l = target.lower()
    smooth = Smoother()
    last_seen = 0.0
    samples = 0
    history: list[tuple[float, float]] = []  # (time, smoothed rssi)
    best = -999.0

    def on_adv(device, adv):
        nonlocal last_seen, samples
        name = (adv.local_name or device.name or "").lower()
        hit = device.address.lower() == target_l if by_address else target_l in name
        if hit:
            smooth.add(adv.rssi)
            last_seen = time.monotonic()
            samples += 1

    kind = "address" if by_address else "name containing"
    print(f"Tracking {kind} '{target}'. Walk slowly, pause 3-5 s at each spot; Ctrl+C to stop.")
    print("Watch the dBm number: closer to 0 is closer (-60 beats -90).\n")
    async with BleakScanner(detection_callback=on_adv):
        while True:
            await asyncio.sleep(0.5)
            now = time.monotonic()
            if smooth.value is None:
                line = f"waiting for first signal... ({now - last_seen if last_seen else 0:.0f}s)"
            elif now - last_seen > 10:
                line = f"lost signal for {now - last_seen:.0f}s - go back to where it was stronger (best {best:.0f} dBm)"
            else:
                v = smooth.value
                best = max(best, v)
                history.append((now, v))
                history[:] = [h for h in history if now - h[0] <= 6]
                delta = v - history[0][1]
                trend = "^ WARMER" if delta >= 2 else "v colder" if delta <= -2 else "- steady"
                label, bar = proximity(v)
                bell = "\a" if v >= -55 else ""
                line = (f"{v:6.1f} dBm [{'#' * bar:<40}] {trend:<8}  best {best:.0f}  "
                        f"{label}  ({samples} pings){bell}")
            sys.stdout.write("\r" + line.ljust(118))
            sys.stdout.flush()


async def survey(target: str, seconds: float) -> None:
    """Measure one spot at a time, then rank the spots. Steadier than the live meter."""
    by_address = is_address(target)
    target_l = target.lower()
    readings: list[int] = []

    def on_adv(device, adv):
        name = (adv.local_name or device.name or "").lower()
        if (device.address.lower() == target_l) if by_address else (target_l in name):
            readings.append(adv.rssi)

    results: list[tuple[str, int, float | None]] = []
    print(f"Survey mode for '{target}'. At each spot, type a label (e.g. 'bedroom by bed')")
    print(f"and press Enter, then hold the laptop still for {seconds:.0f}s. Blank label = done.\n")
    async with BleakScanner(detection_callback=on_adv):
        while True:
            label = (await asyncio.to_thread(input, "spot> ")).strip()
            if not label:
                break
            readings.clear()
            for left in range(int(seconds), 0, -1):
                sys.stdout.write(f"\r  measuring... {left:2d}s  ({len(readings)} pings)   ")
                sys.stdout.flush()
                await asyncio.sleep(1)
            got = sorted(readings)
            med = float(got[len(got) // 2]) if got else None
            results.append((label, len(got), med))
            print(f"\r  {label}: " + (f"{med:.0f} dBm from {len(got)} pings" if got else "NOT HEARD") + " " * 20)
            _print_ranking(results)

    _print_ranking(results, final=True)


def _print_ranking(results, final: bool = False) -> None:
    heard = sorted((r for r in results if r[2] is not None), key=lambda r: -r[2])
    if not final and len(results) < 2:
        return
    print("\n  Ranking so far (strongest first):" if not final else "\nFinal ranking (strongest first):")
    for label, n, med in heard:
        print(f"    {med:6.0f} dBm  {label}  ({n} pings)")
    for label, _, _ in (r for r in results if r[2] is None):
        print(f"      ----    {label}  (not heard)")
    if final and heard:
        print(f"\nSearch around '{heard[0][0]}' first, then survey smaller spots inside it.")
    if final and not heard and results:
        print("\nNot heard anywhere: the battery may be dead, or it reconnected to your phone.")
    print()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lock", metavar="NAME_OR_ADDRESS",
                   help='track one device, e.g. --lock "Fitbit Air" (name survives address changes)')
    p.add_argument("--survey", metavar="NAME_OR_ADDRESS",
                   help='measure spot by spot and rank them, e.g. --survey "Fitbit Air"')
    p.add_argument("--seconds", type=float, default=15, help="scan duration (default 15)")
    p.add_argument("--all", action="store_true", help="list every device, not just likely Fitbits")
    args = p.parse_args()
    try:
        if args.survey:
            coro = survey(args.survey, args.seconds if args.seconds != 15 else 8)
        elif args.lock:
            coro = lock(args.lock)
        else:
            coro = scan(args.seconds, args.all)
        asyncio.run(coro)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
