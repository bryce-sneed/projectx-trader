"""
Core data models shared across the client and the bot framework.

These are deliberately generic — OHLC bars, orders, positions, fills. Nothing here encodes
a trading strategy; bring your own (see the README "Bring your own strategy" section).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Side(Enum):
    """Order / position side."""
    BUY = "BUY"
    SELL = "SELL"

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


class OrderType(Enum):
    """Supported order types."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


@dataclass
class Bar:
    """A single OHLC(V) price bar."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2


@dataclass
class Account:
    """A tradable account as reported by the firm."""
    account_id: int
    name: str
    balance: float = 0.0
    can_trade: bool = True
    is_simulated: bool = False


@dataclass
class Order:
    """An order acknowledgement returned by the gateway."""
    order_id: str
    side: Side
    order_type: OrderType
    symbol: str
    quantity: int
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: str = ""
    fill_price: Optional[float] = None
    position_id: Optional[int] = None


@dataclass
class Position:
    """An open position on the account."""
    symbol: str
    quantity: int          # signed: positive = long, negative = short
    avg_price: float
    position_id: Optional[int] = None

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0


@dataclass
class Fill:
    """A completed execution (a trade leg) reported by the gateway."""
    fill_id: str
    side: Side
    symbol: str
    price: float
    quantity: int
    timestamp: Optional[datetime] = None


@dataclass
class BracketOrder:
    """An entry plus its protective stop and target, managed as one unit."""
    side: Side
    symbol: str
    quantity: int
    entry_type: OrderType = OrderType.MARKET
    entry_price: Optional[float] = None   # None for MARKET
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    tag: str = ""

    @property
    def risk_points(self) -> Optional[float]:
        if self.entry_price is None or self.stop_price is None:
            return None
        return abs(self.entry_price - self.stop_price)
