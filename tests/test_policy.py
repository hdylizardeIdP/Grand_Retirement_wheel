"""Policy decision tests.

Pure-function tests: synthesize a cycle + config + chain, call ``decide``,
assert the returned action. No broker, no DB (except a frozen Cycle
dataclass constructed by hand).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from wheel.broker.client import OptionContract
from wheel.config import TickerConfig
from wheel.policy.policy import (
    SellCashSecuredPut,
    SellCoveredCall,
    _mid_price,
    _pick_by_delta,
    decide,
)
from wheel.store.db import Cycle, Leg
from wheel.store.schema import (
    CYCLE_STATE_HOLDING,
    CYCLE_STATE_NO_SHARES,
    LEG_STATUS_OPEN,
    LEG_TYPE_CSP,
    LEG_TYPE_SHARES,
)

TODAY = date(2026, 5, 16)


def _cfg(**overrides: object) -> TickerConfig:
    base = dict(
        ticker="AAPL",
        enabled=True,
        target_delta=0.30,
        dte_min=30,
        dte_max=45,
        min_credit=0.50,
        max_contracts=1,
    )
    base.update(overrides)
    return TickerConfig(**base)  # type: ignore[arg-type]


def _cycle(state: str, id: int = 1, ticker: str = "AAPL") -> Cycle:
    return Cycle(
        id=id,
        ticker=ticker,
        state=state,
        started_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        ended_at=None,
        realized_pnl=Decimal("0"),
    )


def _put(
    strike: str,
    delta: float,
    *,
    dte: int = 35,
    bid: str = "1.20",
    ask: str = "1.30",
) -> OptionContract:
    return OptionContract(
        symbol=f"AAPL___P{strike}",
        underlying="AAPL",
        expiry=TODAY + timedelta(days=dte),
        strike=Decimal(strike),
        option_type="PUT",
        bid=Decimal(bid),
        ask=Decimal(ask),
        delta=delta,
        open_interest=500,
        volume=100,
    )


def _call(
    strike: str,
    delta: float,
    *,
    dte: int = 35,
    bid: str = "1.20",
    ask: str = "1.30",
) -> OptionContract:
    return OptionContract(
        symbol=f"AAPL___C{strike}",
        underlying="AAPL",
        expiry=TODAY + timedelta(days=dte),
        strike=Decimal(strike),
        option_type="CALL",
        bid=Decimal(bid),
        ask=Decimal(ask),
        delta=delta,
        open_interest=500,
        volume=100,
    )


# --- CSP path ---------------------------------------------------------------


def test_no_shares_picks_target_delta_csp() -> None:
    # target_delta=0.30; contract at |Δ|=0.29 is closest.
    chain = [
        _put("140", -0.15),
        _put("145", -0.29),
        _put("150", -0.42),
    ]
    action = decide(
        cycle=_cycle(CYCLE_STATE_NO_SHARES),
        config=_cfg(),
        chain=chain,
        cost_basis=None,
        today=TODAY,
    )
    assert isinstance(action, SellCashSecuredPut)
    assert action.contract.strike == Decimal("145")
    # mid = (1.20 + 1.30) / 2 = 1.25
    assert action.limit_price == Decimal("1.25")
    assert action.contracts == 1


def test_no_cycle_treated_as_no_shares() -> None:
    chain = [_put("145", -0.30)]
    action = decide(
        cycle=None,
        config=_cfg(),
        chain=chain,
        cost_basis=None,
        today=TODAY,
    )
    assert isinstance(action, SellCashSecuredPut)


# --- CC path ----------------------------------------------------------------


def test_holding_picks_target_delta_cc() -> None:
    chain = [
        _call("150", 0.42),
        _call("155", 0.31),
        _call("160", 0.18),
    ]
    action = decide(
        cycle=_cycle(CYCLE_STATE_HOLDING),
        config=_cfg(),
        chain=chain,
        cost_basis=Decimal("149.00"),
        today=TODAY,
    )
    assert isinstance(action, SellCoveredCall)
    assert action.contract.strike == Decimal("155")


def test_cc_strikes_below_cost_basis_are_filtered_out() -> None:
    # 150 is the delta-closest but sits below cost basis; policy must pick 160.
    chain = [
        _call("150", 0.31, bid="2.00", ask="2.10"),
        _call("160", 0.18, bid="1.00", ask="1.10"),
    ]
    action = decide(
        cycle=_cycle(CYCLE_STATE_HOLDING),
        config=_cfg(),
        chain=chain,
        cost_basis=Decimal("155.00"),
        today=TODAY,
    )
    assert isinstance(action, SellCoveredCall)
    assert action.contract.strike == Decimal("160")


def test_cc_without_cost_basis_returns_none() -> None:
    action = decide(
        cycle=_cycle(CYCLE_STATE_HOLDING),
        config=_cfg(),
        chain=[_call("155", 0.30)],
        cost_basis=None,
        today=TODAY,
    )
    assert action is None


# --- rejection cases --------------------------------------------------------


def test_empty_chain_returns_none() -> None:
    action = decide(
        cycle=_cycle(CYCLE_STATE_NO_SHARES),
        config=_cfg(),
        chain=[],
        cost_basis=None,
        today=TODAY,
    )
    assert action is None


def test_credit_floor_returns_none() -> None:
    chain = [
        _put("145", -0.30, bid="0.10", ask="0.15"),
        _put("140", -0.15, bid="0.05", ask="0.08"),
    ]
    action = decide(
        cycle=_cycle(CYCLE_STATE_NO_SHARES),
        config=_cfg(min_credit=0.50),
        chain=chain,
        cost_basis=None,
        today=TODAY,
    )
    assert action is None


def test_disabled_ticker_returns_none() -> None:
    action = decide(
        cycle=_cycle(CYCLE_STATE_NO_SHARES),
        config=_cfg(enabled=False),
        chain=[_put("145", -0.30)],
        cost_basis=None,
        today=TODAY,
    )
    assert action is None


def test_open_leg_blocks_new_action() -> None:
    cycle = _cycle(CYCLE_STATE_NO_SHARES)
    open_leg = Leg(
        id=42,
        cycle_id=cycle.id,
        type=LEG_TYPE_CSP,
        status=LEG_STATUS_OPEN,
        strike=Decimal("145"),
        expiry=date(2026, 6, 19),
        contracts=1,
        option_symbol="AAPL___P145",
        shares=None,
        cost_basis=None,
        premium=Decimal("1.25"),
        fees=Decimal("0.65"),
        schwab_order_id="ORD-1",
        closing_order_id=None,
        opened_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        closed_at=None,
    )
    action = decide(
        cycle=cycle,
        config=_cfg(),
        chain=[_put("145", -0.30)],
        cost_basis=None,
        today=TODAY,
        open_legs=[open_leg],
    )
    assert action is None


def test_open_shares_leg_does_not_block_new_cc() -> None:
    # SHARES legs represent the underlying position, not an option we sold —
    # they must not suppress selling a covered call.
    cycle = _cycle(CYCLE_STATE_HOLDING)
    shares_leg = Leg(
        id=1,
        cycle_id=cycle.id,
        type=LEG_TYPE_SHARES,
        status=LEG_STATUS_OPEN,
        strike=None,
        expiry=None,
        contracts=None,
        option_symbol=None,
        shares=100,
        cost_basis=Decimal("149.00"),
        premium=Decimal("0"),
        fees=Decimal("0"),
        schwab_order_id=None,
        closing_order_id=None,
        opened_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        closed_at=None,
    )
    action = decide(
        cycle=cycle,
        config=_cfg(),
        chain=[_call("155", 0.30)],
        cost_basis=Decimal("149.00"),
        today=TODAY,
        open_legs=[shares_leg],
    )
    assert isinstance(action, SellCoveredCall)


# --- DTE window / chain filtering ------------------------------------------


def test_contracts_outside_dte_window_are_filtered() -> None:
    chain = [
        _put("145", -0.30, dte=10),   # too soon
        _put("145", -0.30, dte=35),   # good
        _put("145", -0.30, dte=60),   # too far
    ]
    action = decide(
        cycle=_cycle(CYCLE_STATE_NO_SHARES),
        config=_cfg(dte_min=30, dte_max=45),
        chain=chain,
        cost_basis=None,
        today=TODAY,
    )
    assert isinstance(action, SellCashSecuredPut)
    assert (action.contract.expiry - TODAY).days == 35


def test_contracts_with_wrong_option_type_are_filtered() -> None:
    chain = [
        _call("145", 0.30, bid="1.20", ask="1.30"),   # wrong type on CSP path
        _put("145", -0.30, bid="1.20", ask="1.30"),
    ]
    action = decide(
        cycle=_cycle(CYCLE_STATE_NO_SHARES),
        config=_cfg(),
        chain=chain,
        cost_basis=None,
        today=TODAY,
    )
    assert isinstance(action, SellCashSecuredPut)
    assert action.contract.option_type == "PUT"


def test_contracts_with_missing_delta_are_skipped() -> None:
    chain = [
        OptionContract(
            symbol="AAPL___P145_nogreeks",
            underlying="AAPL",
            expiry=TODAY + timedelta(days=35),
            strike=Decimal("145"),
            option_type="PUT",
            bid=Decimal("1.20"),
            ask=Decimal("1.30"),
            delta=None,
            open_interest=100,
            volume=10,
        ),
        _put("150", -0.42),
    ]
    action = decide(
        cycle=_cycle(CYCLE_STATE_NO_SHARES),
        config=_cfg(),
        chain=chain,
        cost_basis=None,
        today=TODAY,
    )
    assert isinstance(action, SellCashSecuredPut)
    assert action.contract.strike == Decimal("150")


# --- helpers ----------------------------------------------------------------


def test_mid_price_rounds_down_to_penny() -> None:
    # (1.23 + 1.28) / 2 = 1.255 → 1.25 with ROUND_DOWN
    contract = _put("145", -0.30, bid="1.23", ask="1.28")
    assert _mid_price(contract) == Decimal("1.25")


def test_pick_by_delta_returns_none_when_all_below_credit_floor() -> None:
    chain = [
        _put("145", -0.30, bid="0.05", ask="0.10"),
        _put("140", -0.15, bid="0.02", ask="0.05"),
    ]
    result = _pick_by_delta(chain, target_delta=0.30, min_credit=Decimal("0.50"))
    assert result is None


def test_pick_by_delta_prefers_closer_delta_over_higher_credit() -> None:
    # Selection is delta-anchored, not price-maximizing: closer |Δ| wins.
    chain = [
        _put("140", -0.10, bid="2.00", ask="2.10"),  # rich, far from delta
        _put("145", -0.29, bid="0.60", ask="0.70"),  # near target, thinner
    ]
    result = _pick_by_delta(chain, target_delta=0.30, min_credit=Decimal("0.50"))
    assert result is not None
    assert result.strike == Decimal("145")
