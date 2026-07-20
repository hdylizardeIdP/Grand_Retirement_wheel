"""Strategy policy — pure functions, no broker / no DB writes.

Given a cycle's current state, market data, and the per-ticker config, return
a proposed action (or ``None`` if nothing should happen this tick). The
executor layer is responsible for safety checks and order placement.

Selection rule v1: pick the chain contract whose absolute delta is closest to
``target_delta`` within ``[dte_min, dte_max]``, subject to ``min_credit``.
IV-rank and skew-aware selection is out of scope for v1.

Design notes:

* ``cycle=None`` is treated as "no shares yet" — we propose the opening CSP.
  The coordinator layer is responsible for creating the cycle row before
  handing the action to the executor.
* ``open_legs`` blocks stacking: if any option leg is still open on this
  cycle, we return ``None``. The reconciler must clear it (expiry, assigned,
  bought-to-close) before we sell another contract.
* CC strike floor (``strike >= cost_basis``) is also enforced in the
  executor as a hard safety rule; we filter it here so policy doesn't
  propose actions that will always be rejected.
* Limit price = mid ((bid+ask)/2), quantized to 0.01. Conservative for a
  sell — the executor / operator may reprice, but v1 keeps it deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Sequence, Union

from wheel.broker.client import OptionContract
from wheel.config import TickerConfig
from wheel.store.db import Cycle, Leg
from wheel.store.schema import (
    CYCLE_STATE_HOLDING,
    CYCLE_STATE_NO_SHARES,
    LEG_TYPE_CC,
    LEG_TYPE_CSP,
)


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

_PENNY = Decimal("0.01")


def decide(
    *,
    cycle: Cycle | None,
    config: TickerConfig,
    chain: list[OptionContract],
    cost_basis: Decimal | None,
    today: date,
    open_legs: Sequence[Leg] = (),
) -> ProposedAction | None:
    """Return the next action for a ticker, or ``None`` if no action.

    Args:
        cycle: Open cycle for the ticker, or ``None`` if no cycle exists yet.
        config: Per-ticker parameters.
        chain: Option chain candidates. Filtered defensively for option type
            and DTE window inside this function; caller pre-filtering is a
            hint, not a contract.
        cost_basis: Per-share cost basis if shares are held; required when the
            cycle is in the ``holding`` state.
        today: Reference date for DTE math.
        open_legs: Currently-open legs on this cycle. Any open option leg
            suppresses new proposals (don't stack).

    Returns:
        A :class:`SellCashSecuredPut`, :class:`SellCoveredCall`, or ``None``.
    """
    if not config.enabled:
        return None

    if any(leg.type in (LEG_TYPE_CSP, LEG_TYPE_CC) for leg in open_legs):
        return None

    state = cycle.state if cycle is not None else CYCLE_STATE_NO_SHARES

    if state == CYCLE_STATE_NO_SHARES:
        candidates = _filter_chain(
            chain,
            option_type="PUT",
            today=today,
            dte_min=config.dte_min,
            dte_max=config.dte_max,
        )
        pick = _pick_by_delta(
            candidates,
            target_delta=config.target_delta,
            min_credit=Decimal(str(config.min_credit)),
        )
        if pick is None:
            return None
        return SellCashSecuredPut(
            ticker=config.ticker,
            contract=pick,
            contracts=config.max_contracts,
            limit_price=_mid_price(pick),
        )

    if state == CYCLE_STATE_HOLDING:
        if cost_basis is None:
            # We're holding shares but the caller didn't tell us the basis —
            # refuse to propose a CC we can't safety-check.
            return None
        candidates = _filter_chain(
            chain,
            option_type="CALL",
            today=today,
            dte_min=config.dte_min,
            dte_max=config.dte_max,
        )
        candidates = [c for c in candidates if c.strike >= cost_basis]
        pick = _pick_by_delta(
            candidates,
            target_delta=config.target_delta,
            min_credit=Decimal(str(config.min_credit)),
        )
        if pick is None:
            return None
        return SellCoveredCall(
            ticker=config.ticker,
            contract=pick,
            contracts=config.max_contracts,
            limit_price=_mid_price(pick),
        )

    return None


def _filter_chain(
    chain: list[OptionContract],
    *,
    option_type: str,
    today: date,
    dte_min: int,
    dte_max: int,
) -> list[OptionContract]:
    earliest = today + timedelta(days=dte_min)
    latest = today + timedelta(days=dte_max)
    return [
        c for c in chain
        if c.option_type == option_type
        and earliest <= c.expiry <= latest
    ]


def _pick_by_delta(
    chain: list[OptionContract],
    *,
    target_delta: float,
    min_credit: Decimal,
) -> OptionContract | None:
    """Return the contract whose |delta| is closest to ``target_delta`` and
    whose mid >= ``min_credit``. Returns ``None`` if none qualify."""
    eligible = [
        c for c in chain
        if c.delta is not None and _mid_price(c) >= min_credit
    ]
    if not eligible:
        return None
    # ``delta`` is checked for None above; assert for the type checker.
    return min(eligible, key=lambda c: abs(abs(c.delta) - target_delta))  # type: ignore[arg-type]


def _mid_price(contract: OptionContract) -> Decimal:
    mid = (contract.bid + contract.ask) / Decimal("2")
    return mid.quantize(_PENNY, rounding=ROUND_DOWN)
