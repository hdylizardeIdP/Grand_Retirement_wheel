"""SQLite access helpers.

Thin wrapper around ``sqlite3`` — no ORM. The :class:`Store` owns the
connection and exposes typed methods the rest of the app uses. Migrations are
trivial (apply ``schema.DDL``); we'll add a real migration runner only if the
schema actually evolves.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator


@dataclass(frozen=True)
class Cycle:
    id: int
    ticker: str
    state: str
    started_at: datetime
    ended_at: datetime | None
    realized_pnl: Decimal


@dataclass(frozen=True)
class Leg:
    id: int
    cycle_id: int
    type: str
    status: str
    strike: Decimal | None
    expiry: date | None
    contracts: int | None
    option_symbol: str | None
    shares: int | None
    cost_basis: Decimal | None
    premium: Decimal
    fees: Decimal
    schwab_order_id: str | None
    closing_order_id: str | None
    opened_at: datetime
    closed_at: datetime | None


@dataclass(frozen=True)
class Event:
    id: int
    ts: datetime
    cycle_id: int | None
    leg_id: int | None
    kind: str
    detail: dict[str, Any] | None


class Store:
    """SQLite-backed wheel state store."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: sqlite3.Connection | None = None

    # --- lifecycle ---------------------------------------------------------

    def connect(self) -> None:
        """Open the connection, enable foreign keys, apply schema."""
        raise NotImplementedError

    def close(self) -> None:
        """Close the underlying connection."""
        raise NotImplementedError

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager wrapping a single transaction."""
        raise NotImplementedError
        yield  # pragma: no cover

    # --- cycles ------------------------------------------------------------

    def get_open_cycle(self, ticker: str) -> Cycle | None:
        """Return the open cycle for ``ticker`` or ``None``."""
        raise NotImplementedError

    def start_cycle(self, ticker: str, state: str) -> Cycle:
        """Create a new open cycle. Fails if one already exists for the ticker."""
        raise NotImplementedError

    def set_cycle_state(self, cycle_id: int, state: str) -> None:
        """Update the cycle's state (no_shares ↔ holding)."""
        raise NotImplementedError

    def close_cycle(self, cycle_id: int, realized_pnl: Decimal) -> None:
        """Mark the cycle ended and record its realized P&L."""
        raise NotImplementedError

    def list_cycles(self, ticker: str | None = None) -> list[Cycle]:
        """All cycles, optionally filtered by ticker, newest first."""
        raise NotImplementedError

    # --- legs --------------------------------------------------------------

    def add_leg(self, leg: Leg) -> Leg:
        """Insert a leg. Returns the row with its assigned id."""
        raise NotImplementedError

    def update_leg_status(
        self,
        leg_id: int,
        status: str,
        *,
        closing_order_id: str | None = None,
        closed_at: datetime | None = None,
    ) -> None:
        """Transition a leg to a terminal status."""
        raise NotImplementedError

    def find_leg_by_schwab_order(self, order_id: str) -> Leg | None:
        """Look up a leg by its opening Schwab order id."""
        raise NotImplementedError

    def list_open_legs(self, cycle_id: int) -> list[Leg]:
        """Return open legs for a cycle."""
        raise NotImplementedError

    # --- events ------------------------------------------------------------

    def record_event(
        self,
        kind: str,
        *,
        cycle_id: int | None = None,
        leg_id: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> Event:
        """Append an audit event."""
        raise NotImplementedError

    def list_events(self, cycle_id: int | None = None) -> list[Event]:
        """Return events, optionally filtered by cycle, newest first."""
        raise NotImplementedError
