"""Strategy policy — pure functions, no broker / no DB writes.

Given a cycle's current state, market data, and the per-ticker config, return
a proposed action (or ``None`` if nothing should happen this tick). The
executor layer is responsible for safety checks and order placement.

Selection rule v1: pick the chain contract whose absolute delta is closest to
``target_delta`` within ``[dte_min, dte_max]``, subject to ``min_credit``.
IV-rank and skew-aware selection is out of scope for v1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Union

from wheel.broker.client import OptionContract
from wheel.config import TickerConfig
from wheel.store.db import Cycle


@dataclass(frozen=True)
class SellCashSecuredPut:
    ticker: str
    contract: OptionContract
    contracts: int
    limit_price: Decimal


@dataclass(frozen=True)
class SellCoveredCall:
    ticker: str
    contract: OptionContract
    contracts: int
    limit_price: Decimal


ProposedAction = Union[SellCashSecuredPut, SellCoveredCall]


def decide(
    *,
    cycle: Cycle | None,
    config: TickerConfig,
    chain: list[OptionContract],
    cost_basis: Decimal | None,
    today: date,
) -> ProposedAction | None:
    """Return the next action for a ticker, or ``None`` if no action.

    Args:
        cycle: Open cycle for the ticker, or ``None`` if no cycle exists.
        config: Per-ticker parameters.
        chain: Filtered option chain (CSP candidates if state is ``no_shares``,
            CC candidates if state is ``holding``).
        cost_basis: Per-share cost basis if shares are held; ``None`` otherwise.
            Required to enforce the CC strike floor.
        today: Reference date for DTE math.

    Returns:
        A :class:`SellCashSecuredPut` or :class:`SellCoveredCall`, or ``None``
        if no contract satisfies the constraints, the ticker has an open
        opposite leg, or the ticker is disabled.
    """
    raise NotImplementedError


def _pick_by_delta(
    chain: list[OptionContract],
    *,
    target_delta: float,
    min_credit: Decimal,
) -> OptionContract | None:
    """Return the contract whose |delta| is closest to ``target_delta`` and
    whose mid >= ``min_credit``. Returns ``None`` if none qualify."""
    raise NotImplementedError
