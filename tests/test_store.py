"""Tests for the SQLite store."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from wheel.store.db import Cycle, Leg, Store
from wheel.store.schema import (
    CYCLE_STATE_HOLDING,
    CYCLE_STATE_NO_SHARES,
    LEG_STATUS_ASSIGNED,
    LEG_STATUS_CLOSED,
    LEG_STATUS_EXPIRED,
    LEG_STATUS_OPEN,
    LEG_TYPE_CC,
    LEG_TYPE_CSP,
    LEG_TYPE_SHARES,
)


def _draft_csp_leg(cycle_id: int, **overrides: object) -> Leg:
    base = dict(
        id=0,
        cycle_id=cycle_id,
        type=LEG_TYPE_CSP,
        status=LEG_STATUS_OPEN,
        strike=Decimal("150.00"),
        expiry=date(2026, 6, 19),
        contracts=1,
        option_symbol="AAPL  260619P00150000",
        shares=None,
        cost_basis=None,
        premium=Decimal("1.25"),
        fees=Decimal("0.65"),
        schwab_order_id="ORD-1",
        closing_order_id=None,
        opened_at=datetime(2026, 5, 16, 14, 30, tzinfo=timezone.utc),
        closed_at=None,
    )
    base.update(overrides)
    return Leg(**base)  # type: ignore[arg-type]


# --- lifecycle / connection -------------------------------------------------


def test_connect_is_idempotent(store: Store) -> None:
    # conftest's fixture already calls connect(); a second call is a no-op.
    store.connect()
    store.connect()
    assert store.get_open_cycle("AAPL") is None


def test_close_then_use_raises(tmp_path: Path) -> None:
    s = Store(tmp_path / "wheel.db")
    s.connect()
    s.close()
    with pytest.raises(RuntimeError, match="not connected"):
        s.get_open_cycle("AAPL")


def test_transaction_rolls_back_on_error(store: Store) -> None:
    store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    with pytest.raises(RuntimeError):
        with store.transaction() as conn:
            conn.execute(
                "INSERT INTO cycles (ticker, state, started_at) VALUES (?, ?, ?)",
                ("MSFT", CYCLE_STATE_NO_SHARES, "2026-05-16T00:00:00+00:00"),
            )
            raise RuntimeError("boom")
    # The MSFT insert above must not have persisted.
    assert store.get_open_cycle("MSFT") is None
    assert store.get_open_cycle("AAPL") is not None


# --- cycles -----------------------------------------------------------------


def test_start_and_get_open_cycle(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    assert cycle.id > 0
    assert cycle.ticker == "AAPL"
    assert cycle.state == CYCLE_STATE_NO_SHARES
    assert cycle.ended_at is None
    assert cycle.realized_pnl == Decimal("0")
    assert cycle.started_at.tzinfo is timezone.utc

    fetched = store.get_open_cycle("AAPL")
    assert fetched is not None
    assert fetched.id == cycle.id
    assert fetched.started_at == cycle.started_at


def test_start_cycle_rejects_duplicate_open(store: Store) -> None:
    store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    with pytest.raises(sqlite3.IntegrityError):
        store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)


def test_start_cycle_allows_new_cycle_after_close(store: Store) -> None:
    first = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    store.close_cycle(first.id, Decimal("125.00"))
    second = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    assert second.id != first.id
    assert store.get_open_cycle("AAPL") is not None


def test_set_cycle_state(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    store.set_cycle_state(cycle.id, CYCLE_STATE_HOLDING)
    refreshed = store.get_open_cycle("AAPL")
    assert refreshed is not None
    assert refreshed.state == CYCLE_STATE_HOLDING


def test_set_cycle_state_rejects_invalid_value(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    with pytest.raises(sqlite3.IntegrityError):
        store.set_cycle_state(cycle.id, "garbage")


def test_close_cycle_records_realized_pnl(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_HOLDING)
    store.close_cycle(cycle.id, Decimal("412.75"))
    [closed] = store.list_cycles(ticker="AAPL")
    assert closed.ended_at is not None
    assert closed.realized_pnl == Decimal("412.75")
    assert store.get_open_cycle("AAPL") is None


def test_list_cycles_newest_first(store: Store) -> None:
    a = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    store.close_cycle(a.id, Decimal("10"))
    b = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    store.close_cycle(b.id, Decimal("20"))
    c = store.start_cycle("MSFT", CYCLE_STATE_NO_SHARES)
    assert [c.id for c in store.list_cycles()] == [c.id, b.id, a.id]
    assert [c.id for c in store.list_cycles(ticker="AAPL")] == [b.id, a.id]


# --- legs -------------------------------------------------------------------


def test_add_leg_round_trip_preserves_decimal_and_date(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    leg = store.add_leg(
        _draft_csp_leg(
            cycle.id,
            strike=Decimal("147.50"),
            premium=Decimal("1.23"),
            fees=Decimal("0.65"),
        )
    )
    assert leg.id > 0
    assert leg.strike == Decimal("147.50")
    assert leg.premium == Decimal("1.23")
    assert leg.fees == Decimal("0.65")
    assert leg.expiry == date(2026, 6, 19)
    assert leg.opened_at.tzinfo is timezone.utc

    # Confirm the persisted value parses back cleanly via a fresh lookup.
    found = store.find_leg_by_schwab_order("ORD-1")
    assert found is not None
    assert found.id == leg.id
    assert found.strike == Decimal("147.50")


def test_add_leg_check_constraint_csp_requires_strike(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    with pytest.raises(sqlite3.IntegrityError):
        store.add_leg(_draft_csp_leg(cycle.id, strike=None))


def test_add_leg_shares_type_allowed_without_strike(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_HOLDING)
    leg = store.add_leg(
        Leg(
            id=0,
            cycle_id=cycle.id,
            type=LEG_TYPE_SHARES,
            status=LEG_STATUS_OPEN,
            strike=None,
            expiry=None,
            contracts=None,
            option_symbol=None,
            shares=100,
            cost_basis=Decimal("149.37"),
            premium=Decimal("0"),
            fees=Decimal("0"),
            schwab_order_id=None,
            closing_order_id=None,
            opened_at=datetime(2026, 5, 16, 14, 30, tzinfo=timezone.utc),
            closed_at=None,
        )
    )
    assert leg.shares == 100
    assert leg.cost_basis == Decimal("149.37")


def test_update_leg_status_writes_only_supplied_fields(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    leg = store.add_leg(_draft_csp_leg(cycle.id))

    # status-only update preserves closing_order_id / closed_at as NULL.
    store.update_leg_status(leg.id, LEG_STATUS_EXPIRED)
    expired = store.find_leg_by_schwab_order("ORD-1")
    assert expired is not None
    assert expired.status == LEG_STATUS_EXPIRED
    assert expired.closing_order_id is None
    assert expired.closed_at is None

    # buy-to-close path populates the closing order id and timestamp.
    closed_at = datetime(2026, 5, 17, 13, 0, tzinfo=timezone.utc)
    store.update_leg_status(
        leg.id,
        LEG_STATUS_CLOSED,
        closing_order_id="ORD-2",
        closed_at=closed_at,
    )
    closed = store.find_leg_by_schwab_order("ORD-1")
    assert closed is not None
    assert closed.status == LEG_STATUS_CLOSED
    assert closed.closing_order_id == "ORD-2"
    assert closed.closed_at == closed_at


def test_update_leg_status_rejects_invalid_status(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    leg = store.add_leg(_draft_csp_leg(cycle.id))
    with pytest.raises(sqlite3.IntegrityError):
        store.update_leg_status(leg.id, "wat")


def test_list_open_legs_returns_only_open(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    open_leg = store.add_leg(_draft_csp_leg(cycle.id, schwab_order_id="ORD-A"))
    assigned_leg = store.add_leg(
        _draft_csp_leg(
            cycle.id,
            schwab_order_id="ORD-B",
            strike=Decimal("145.00"),
            expiry=date(2026, 7, 17),
        )
    )
    store.update_leg_status(assigned_leg.id, LEG_STATUS_ASSIGNED)

    open_ids = [leg.id for leg in store.list_open_legs(cycle.id)]
    assert open_ids == [open_leg.id]


def test_find_leg_by_unknown_order_returns_none(store: Store) -> None:
    assert store.find_leg_by_schwab_order("nope") is None


# --- events -----------------------------------------------------------------


def test_record_event_round_trips_detail_json(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    leg = store.add_leg(_draft_csp_leg(cycle.id))

    event = store.record_event(
        "csp_sold",
        cycle_id=cycle.id,
        leg_id=leg.id,
        detail={"premium": "1.25", "delta": -0.27},
    )
    assert event.id > 0
    assert event.detail == {"premium": "1.25", "delta": -0.27}
    assert event.ts.tzinfo is timezone.utc

    [fetched] = store.list_events(cycle_id=cycle.id)
    assert fetched.id == event.id
    assert fetched.kind == "csp_sold"
    assert fetched.detail == {"premium": "1.25", "delta": -0.27}


def test_record_event_with_no_detail(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    event = store.record_event("cycle_started", cycle_id=cycle.id)
    assert event.detail is None
    [fetched] = store.list_events()
    assert fetched.detail is None


def test_list_events_newest_first(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    e1 = store.record_event("a", cycle_id=cycle.id)
    e2 = store.record_event("b", cycle_id=cycle.id)
    e3 = store.record_event("c", cycle_id=cycle.id)
    assert [e.id for e in store.list_events(cycle_id=cycle.id)] == [e3.id, e2.id, e1.id]


# --- foreign keys / pragmas -------------------------------------------------


def test_foreign_keys_enforced(store: Store) -> None:
    # Inserting a leg with a non-existent cycle id should fail because
    # PRAGMA foreign_keys is ON.
    with pytest.raises(sqlite3.IntegrityError):
        store.add_leg(_draft_csp_leg(cycle_id=9999))


# --- write-time rejections --------------------------------------------------


def test_naive_datetime_rejected(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_NO_SHARES)
    naive = datetime(2026, 5, 16, 14, 30)
    with pytest.raises(ValueError, match="timezone-aware"):
        store.add_leg(_draft_csp_leg(cycle.id, opened_at=naive))


def test_cycle_dataclass_is_frozen() -> None:
    cycle = Cycle(
        id=1,
        ticker="AAPL",
        state=CYCLE_STATE_NO_SHARES,
        started_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
        ended_at=None,
        realized_pnl=Decimal("0"),
    )
    with pytest.raises(Exception):
        cycle.state = CYCLE_STATE_HOLDING  # type: ignore[misc]


# Sanity that the CC leg type is accepted alongside CSP/SHARES (covers the
# remaining branch of the type CHECK constraint).
def test_cc_leg_can_be_inserted(store: Store) -> None:
    cycle = store.start_cycle("AAPL", CYCLE_STATE_HOLDING)
    leg = store.add_leg(
        _draft_csp_leg(
            cycle.id,
            type=LEG_TYPE_CC,
            strike=Decimal("155.00"),
            schwab_order_id="ORD-CC",
        )
    )
    assert leg.type == LEG_TYPE_CC
