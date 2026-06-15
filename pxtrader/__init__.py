"""
pxtrader — a Python client and automation framework for ProjectX-powered prop-firm
futures platforms (TopstepX and others).

v0.1 ships the REST client (auth, market data, orders, accounts) and core models. The
reliability layer (fast fill confirmation, reconciliation, restart-recovery, watchdog) and the
backtest harness + ``Strategy`` interface land in subsequent releases — see the README roadmap.
"""
from .accounts import AccountClient
from .auth import AuthClient, HeaderManager, LoginResponse, SystemProfile
from .client import ProjectXClient
from .config import DEFAULT_FIRM, PRESETS, FirmConfig, get_firm
from .market_data import MarketDataClient
from .models import (
    Account,
    Bar,
    BracketOrder,
    Fill,
    Order,
    OrderType,
    Position,
    Side,
)
from .orders import OrderClient, OrderError, OrderRequest, OrderResult

__version__ = "0.1.0"

__all__ = [
    # client
    "ProjectXClient",
    "AuthClient",
    "MarketDataClient",
    "OrderClient",
    "AccountClient",
    # auth
    "HeaderManager",
    "LoginResponse",
    "SystemProfile",
    # orders
    "OrderRequest",
    "OrderResult",
    "OrderError",
    # config
    "FirmConfig",
    "get_firm",
    "PRESETS",
    "DEFAULT_FIRM",
    # models
    "Bar",
    "Side",
    "OrderType",
    "Account",
    "Order",
    "Position",
    "Fill",
    "BracketOrder",
    "__version__",
]
