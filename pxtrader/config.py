"""
Firm/endpoint configuration.

ProjectX is the trading gateway that powers TopstepX and a number of other prop-firm
platforms. Each firm exposes the same API shape under its own hostnames, so the endpoints
are kept here as swappable presets instead of being hardcoded in the client. Point the
client at your firm by name (``PROJECTX_FIRM``) or by passing a custom ``FirmConfig``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class FirmConfig:
    """Base URLs for one ProjectX-powered firm.

    Attributes:
        name:      Short identifier (e.g. "topstepx").
        user_api:  Account / order / position REST base (no trailing slash).
        chart_api: Historical + live market-data REST base.
        web:       Public web base (used for version checks, etc.).
    """
    name: str
    user_api: str
    chart_api: str
    web: str


# Built-in presets. Add your firm's ProjectX gateway hostnames here and reference it by name.
PRESETS: dict[str, FirmConfig] = {
    "topstepx": FirmConfig(
        name="topstepx",
        user_api="https://userapi.topstepx.com",
        chart_api="https://chartapi.topstepx.com",
        web="https://topstepx.com",
    ),
}

DEFAULT_FIRM = "topstepx"


def get_firm(name: str | None = None) -> FirmConfig:
    """Resolve a firm preset by name, falling back to ``PROJECTX_FIRM`` then the default."""
    key = (name or os.environ.get("PROJECTX_FIRM") or DEFAULT_FIRM).strip().lower()
    if key not in PRESETS:
        raise KeyError(
            f"Unknown firm preset {key!r}. Known: {sorted(PRESETS)}. "
            f"Add yours to pxtrader/config.PRESETS or pass a custom FirmConfig."
        )
    return PRESETS[key]
