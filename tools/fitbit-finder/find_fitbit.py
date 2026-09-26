#!/usr/bin/env python3
"""Hot/cold Bluetooth finder for a lost Fitbit.

Run it on a laptop, then walk around: the signal bar grows as you get closer.

    pip install bleak
    python find_fitbit.py              # scan: list nearby devices, likely Fitbits first
    python find_fitbit.py --lock ADDR  # track one device with a live hot/cold meter

Before you start, turn Bluetooth OFF on the phone the Fitbit is paired with.
A tracker that is connected to its phone usually stops advertising, so nothing
else can see it.
"""
from __future__ import annotations

import argparse
import asyncio
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
    print("\nPick the best candidate and run:  python find_fitbit.py --lock <address>")
    print("Unsure which it is? Stand next to each candidate spot; the right one gets stronger.")


async def lock(address: str) -> None:
    target = address.lower()
    smooth = Smoother()
    last_seen = 0.0

    def on_adv(device, adv):
        nonlocal last_seen
        if device.address.lower() == target:
            smooth.add(adv.rssi)
            last_seen = time.monotonic()

    print(f"Tracking {address}. Walk slowly and turn in place; Ctrl+C to stop.\n")
    async with BleakScanner(detection_callback=on_adv):
        while True:
            await asyncio.sleep(0.5)
            if smooth.value is None:
                line = "waiting for first signal..."
            elif time.monotonic() - last_seen > 10:
                line = f"lost signal for {time.monotonic() - last_seen:.0f}s - go back to where it was stronger"
            else:
                label, bar = proximity(smooth.value)
                bell = "\a" if smooth.value >= -55 else ""
                line = f"{smooth.value:6.1f} dBm  [{'#' * bar:<40}]  {label}{bell}"
            sys.stdout.write("\r\033[K" + line)
            sys.stdout.flush()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lock", metavar="ADDRESS", help="track one device's signal strength")
    p.add_argument("--seconds", type=float, default=15, help="scan duration (default 15)")
    p.add_argument("--all", action="store_true", help="list every device, not just likely Fitbits")
    args = p.parse_args()
    try:
        asyncio.run(lock(args.lock) if args.lock else scan(args.seconds, args.all))
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
