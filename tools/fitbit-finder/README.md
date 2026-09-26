# Fitbit Finder

Hot/cold Bluetooth finder for a lost Fitbit tracker. It reads the Bluetooth
signal strength (RSSI) of the tracker's advertisements, so you walk around and
follow the signal as it gets stronger.

**Before you start, turn Bluetooth off on the phone the Fitbit is paired with.**
A tracker that is connected to its phone usually stops advertising. If the
battery is dead, no Bluetooth tool can find it.

## Laptop (most reliable)

```bash
pip install bleak
python find_fitbit.py              # list nearby devices, likely Fitbits first
python find_fitbit.py --lock ADDR  # live hot/cold meter for one device
```

On macOS, addresses are UUIDs rather than MAC addresses; paste them as printed.

## Phone (Chrome on Android)

1. In `chrome://flags`, enable **Experimental Web Platform features** and restart Chrome.
2. Open `index.html` over `https://` (e.g. GitHub Pages) or from `localhost`.
3. Tap **Scan**, tap the starred device, turn on sound, and walk. Beeps speed up as you get closer.

iPhone browsers don't support Web Bluetooth; use the laptop script or a BLE
scanner app such as nRF Connect.

## Tips

- Signal bounces off walls and bodies. Move slowly, pause a few seconds, and
  turn in place; follow the trend rather than single readings.
- Can't tell which device it is? The Fitbit's entry disappears when you turn
  the phone's Bluetooth back on and it reconnects.
- Check the last place it synced in the Fitbit app to narrow the search area.
