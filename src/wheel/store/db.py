"""SQLite access helpers.

Thin wrapper around ``sqlite3`` — no ORM. The :class:`Store` owns the
connection and exposes typed methods the rest of the app uses. Migrations are
trivial (apply ``schema.DDL``); we'll add a real migration runner only if the
schema actually evolves.

Conventions:

* Monetary values use :class:`decimal.Decimal` end-to-end. They're stored as
  TEXT and (de)serialized via ``str(...)`` / ``Decimal(...)``.
* All timestamps are timezone-aware UTC. Naive datetimes are rejected at
  write time.
* ``event.detail`` is a free-form JSON dict; callers are responsible for
  passing only JSON-serializable values.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

from wheel.store.schema import apply_schema

logger = logging.getLogger(__name__)


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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dt_to_text(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware (UTC)")
    return dt.astimezone(timezone.utc).isoformat()


def _text_to_dt(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        # Stored values are always tz-aware; a naive value means corruption.
        raise ValueError(f"stored datetime is not tz-aware: {text!r}")
    return dt.astimezone(timezone.utc)


def _opt_dt_to_text(dt: datetime | None) -> str | None:
    return None if dt is None else _dt_to_text(dt)


def _opt_text_to_dt(text: str | None) -> datetime | None:
    return None if text is None else _text_to_dt(text)


def _dec_to_text(value: Decimal) -> str:
    return str(value)


def _opt_dec_to_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _opt_text_to_dec(text: str | None) -> Decimal | None:
    return None if text is None else Decimal(text)


def _opt_date_to_text(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _opt_text_to_date(text: str | None) -> date | None:
    return None if text is None else date.fromisoformat(text)


def _row_to_cycle(row: sqlite3.Row) -> Cycle:
    return Cycle(
        id=row["id"],
        ticker=row["ticker"],
        state=row["state"],
        started_at=_text_to_dt(row["started_at"]),
        ended_at=_opt_text_to_dt(row["ended_at"]),
        realized_pnl=Decimal(row["realized_pnl"]),
    )


def _row_to_leg(row: sqlite3.Row) -> Leg:
    return Leg(
        id=row["id"],
        cycle_id=row["cycle_id"],
        type=row["type"],
        status=row["status"],
        strike=_opt_text_to_dec(row["strike"]),
        expiry=_opt_text_to_date(row["expiry"]),
        contracts=row["contracts"],
        option_symbol=row["option_symbol"],
        shares=row["shares"],
        cost_basis=_opt_text_to_dec(row["cost_basis"]),
        premium=Decimal(row["premium"]),
        fees=Decimal(row["fees"]),
        schwab_order_id=row["schwab_order_id"],
        closing_order_id=row["closing_order_id"],
        opened_at=_text_to_dt(row["opened_at"]),
        closed_at=_opt_text_to_dt(row["closed_at"]),
    )


def _row_to_event(row: sqlite3.Row) -> Event:
    detail_raw = row["detail"]
    return Event(
        id=row["id"],
        ts=_text_to_dt(row["ts"]),
        cycle_id=row["cycle_id"],
        leg_id=row["leg_id"],
        kind=row["kind"],
        detail=None if detail_raw is None else json.loads(detail_raw),
    )


class Store:
    """SQLite-backed wheel state store."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: sqlite3.Connection | None = None

    # --- lifecycle ---------------------------------------------------------

    def connect(self) -> None:
        """Open the connection, enable foreign keys, apply schema. Idempotent."""
        if self._conn is not None:
            return
        # ``check_same_thread=False`` would be needed for multi-threaded use;
        # the wheel bot is single-threaded so we keep the default safety.
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        apply_schema(conn)
        self._conn = conn
        logger.debug("store connected at %s", self._path)

    def close(self) -> None:
        """Close the underlying connection."""
        if self._conn is None:
            return
        self._conn.close()
        self._conn = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Yield the connection inside a single transaction.

        Commits on clean exit, rolls back on exception. Relies on the default
        ``sqlite3`` connection context manager.
        """
        conn = self._require_conn()
        with conn:
            yield conn

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Store is not connected; call connect() first.")
        return self._conn

    # --- cycles ------------------------------------------------------------

    def get_open_cycle(self, ticker: str) -> Cycle | None:
        """Return the open cycle for ``ticker`` or ``None``."""
        conn = self._require_conn()
        row = conn.execute(
            "SELECT * FROM cycles WHERE ticker = ? AND ended_at IS NULL",
            (ticker,),
        ).fetchone()
        return None if row is None else _row_to_cycle(row)

    def start_cycle(self, ticker: str, state: str) -> Cycle:
        """Create a new open cycle. Raises if one already exists for the ticker.

        The uniqueness guarantee comes from the ``ux_cycles_open_ticker``
        partial index; a duplicate raises :class:`sqlite3.IntegrityError`.
        """
        started_at = _utcnow()
        with self.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO cycles (ticker, state, started_at) VALUES (?, ?, ?)",
                (ticker, state, _dt_to_text(started_at)),
            )
            cycle_id = cur.lastrowid
        assert cycle_id is not None
        return Cycle(
            id=cycle_id,
            ticker=ticker,
            state=state,
            started_at=started_at,
            ended_at=None,
            realized_pnl=Decimal("0"),
        )

    def set_cycle_state(self, cycle_id: int, state: str) -> None:
        """Update the cycle's state (no_shares ↔ holding)."""
        with self.transaction() as conn:
            conn.execute(
                "UPDATE cycles SET state = ? WHERE id = ?",
                (state, cycle_id),
            )

    def close_cycle(self, cycle_id: int, realized_pnl: Decimal) -> None:
        """Mark the cycle ended and record its realized P&L."""
        ended_at = _utcnow()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE cycles SET ended_at = ?, realized_pnl = ? WHERE id = ?",
                (_dt_to_text(ended_at), _dec_to_text(realized_pnl), cycle_id),
            )

    def list_cycles(self, ticker: str | None = None) -> list[Cycle]:
        """All cycles, optionally filtered by ticker, newest first."""
        conn = self._require_conn()
        if ticker is None:
            rows = conn.execute("SELECT * FROM cycles ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cycles WHERE ticker = ? ORDER BY id DESC",
                (ticker,),
            ).fetchall()
        return [_row_to_cycle(r) for r in rows]

    # --- legs --------------------------------------------------------------

    def add_leg(self, leg: Leg) -> Leg:
        """Insert a leg. ``leg.id`` is ignored; the returned leg has the real id."""
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO legs (
                    cycle_id, type, status,
                    strike, expiry, contracts, option_symbol,
                    shares, cost_basis,
                    premium, fees,
                    schwab_order_id, closing_order_id,
                    opened_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    leg.cycle_id,
                    leg.type,
                    leg.status,
                    _opt_dec_to_text(leg.strike),
                    _opt_date_to_text(leg.expiry),
                    leg.contracts,
                    leg.option_symbol,
                    leg.shares,
                    _opt_dec_to_text(leg.cost_basis),
                    _dec_to_text(leg.premium),
                    _dec_to_text(leg.fees),
                    leg.schwab_order_id,
                    leg.closing_order_id,
                    _dt_to_text(leg.opened_at),
                    _opt_dt_to_text(leg.closed_at),
                ),
            )
            leg_id = cur.lastrowid
        assert leg_id is not None
        # Re-read so the returned dataclass exactly matches what's persisted
        # (catches any normalization drift, e.g. tz conversion).
        return self._get_leg(leg_id)

    def _get_leg(self, leg_id: int) -> Leg:
        conn = self._require_conn()
        row = conn.execute("SELECT * FROM legs WHERE id = ?", (leg_id,)).fetchone()
        if row is None:
            raise LookupError(f"leg {leg_id} not found")
        return _row_to_leg(row)

    def update_leg_status(
        self,
        leg_id: int,
        status: str,
        *,
        closing_order_id: str | None = None,
        closed_at: datetime | None = None,
    ) -> None:
        """Transition a leg to a terminal status.

        ``closing_order_id`` and ``closed_at`` are written only when supplied;
        ``None`` leaves the existing value untouched.
        """
        sets: list[str] = ["status = ?"]
        params: list[Any] = [status]
        if closing_order_id is not None:
            sets.append("closing_order_id = ?")
            params.append(closing_order_id)
        if closed_at is not None:
            sets.append("closed_at = ?")
            params.append(_dt_to_text(closed_at))
        params.append(leg_id)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE legs SET {', '.join(sets)} WHERE id = ?",
                params,
            )

    def find_leg_by_schwab_order(self, order_id: str) -> Leg | None:
        """Look up a leg by its opening Schwab order id."""
        conn = self._require_conn()
        row = conn.execute(
            "SELECT * FROM legs WHERE schwab_order_id = ?",
            (order_id,),
        ).fetchone()
        return None if row is None else _row_to_leg(row)

    def list_open_legs(self, cycle_id: int) -> list[Leg]:
        """Return open legs for a cycle."""
        conn = self._require_conn()
        rows = conn.execute(
            "SELECT * FROM legs WHERE cycle_id = ? AND status = 'open' ORDER BY id",
            (cycle_id,),
        ).fetchall()
        return [_row_to_leg(r) for r in rows]

    # --- events ------------------------------------------------------------

    def record_event(
        self,
        kind: str,
        *,
        cycle_id: int | None = None,
        leg_id: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> Event:
        """Append an audit event. ``detail`` must be JSON-serializable."""
        ts = _utcnow()
        detail_text = None if detail is None else json.dumps(detail, sort_keys=True)
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO events (ts, cycle_id, leg_id, kind, detail)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_dt_to_text(ts), cycle_id, leg_id, kind, detail_text),
            )
            event_id = cur.lastrowid
        assert event_id is not None
        return Event(
            id=event_id,
            ts=ts,
            cycle_id=cycle_id,
            leg_id=leg_id,
            kind=kind,
            detail=detail,
        )

    def list_events(self, cycle_id: int | None = None) -> list[Event]:
        """Return events, optionally filtered by cycle, newest first."""
        conn = self._require_conn()
        if cycle_id is None:
            rows = conn.execute("SELECT * FROM events ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events WHERE cycle_id = ? ORDER BY id DESC",
                (cycle_id,),
            ).fetchall()
        return [_row_to_event(r) for r in rows]
