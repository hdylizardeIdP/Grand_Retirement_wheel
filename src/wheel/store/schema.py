"""SQLite schema for the wheel store.

Three tables:

* ``cycles`` — one row per open wheel cycle on a ticker. A cycle starts when
  we sell the first CSP and ends when we get called away (or manually close).
* ``legs`` — every option contract sold or share lot held within a cycle.
* ``events`` — append-only audit log of every state transition.

Monetary values are stored as TEXT (decimal strings) to avoid float drift;
the application layer converts to :class:`decimal.Decimal`. Dates/times are
ISO-8601 strings in UTC.

States and enums are enforced via CHECK constraints; we want bad data to fail
loudly at write time rather than corrupt the audit log.
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

# Cycle states. Mirrors the strategy state machine.
CYCLE_STATE_NO_SHARES = "no_shares"     # selling CSPs
CYCLE_STATE_HOLDING = "holding"         # selling CCs
CYCLE_STATES = (CYCLE_STATE_NO_SHARES, CYCLE_STATE_HOLDING)

# Leg types.
LEG_TYPE_CSP = "CSP"
LEG_TYPE_CC = "CC"
LEG_TYPE_SHARES = "SHARES"
LEG_TYPES = (LEG_TYPE_CSP, LEG_TYPE_CC, LEG_TYPE_SHARES)

# Leg statuses.
LEG_STATUS_OPEN = "open"
LEG_STATUS_CLOSED = "closed"              # bought to close, or shares sold flat
LEG_STATUS_ASSIGNED = "assigned"          # short put assigned → shares
LEG_STATUS_EXPIRED = "expired"            # option expired worthless
LEG_STATUS_CALLED_AWAY = "called_away"    # short call exercised → shares gone
LEG_STATUSES = (
    LEG_STATUS_OPEN,
    LEG_STATUS_CLOSED,
    LEG_STATUS_ASSIGNED,
    LEG_STATUS_EXPIRED,
    LEG_STATUS_CALLED_AWAY,
)

DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS cycles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT    NOT NULL,
    state         TEXT    NOT NULL CHECK (state IN ('no_shares', 'holding')),
    started_at    TEXT    NOT NULL,                   -- ISO-8601 UTC
    ended_at      TEXT,                               -- NULL while open
    realized_pnl  TEXT    NOT NULL DEFAULT '0'        -- decimal string, USD
);

-- At most one open cycle per ticker.
CREATE UNIQUE INDEX IF NOT EXISTS ux_cycles_open_ticker
    ON cycles(ticker) WHERE ended_at IS NULL;

CREATE TABLE IF NOT EXISTS legs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id         INTEGER NOT NULL REFERENCES cycles(id) ON DELETE RESTRICT,
    type             TEXT    NOT NULL CHECK (type IN ('CSP', 'CC', 'SHARES')),
    status           TEXT    NOT NULL CHECK (
                         status IN ('open', 'closed', 'assigned',
                                    'expired', 'called_away')),
    -- Option-specific (NULL for SHARES legs).
    strike           TEXT,                            -- decimal string
    expiry           TEXT,                            -- ISO-8601 date
    contracts        INTEGER,                         -- positive count
    option_symbol    TEXT,                            -- OCC symbol
    -- Shares-specific (NULL for option legs).
    shares           INTEGER,
    cost_basis       TEXT,                            -- decimal string per share
    -- Cash flow.
    premium          TEXT    NOT NULL DEFAULT '0',    -- decimal string, USD (net)
    fees             TEXT    NOT NULL DEFAULT '0',    -- decimal string, USD
    -- Broker link.
    schwab_order_id  TEXT,                            -- opening order
    closing_order_id TEXT,
    opened_at        TEXT    NOT NULL,                -- ISO-8601 UTC
    closed_at        TEXT,
    CHECK (
        (type = 'SHARES' AND shares IS NOT NULL)
        OR (type IN ('CSP', 'CC')
            AND strike IS NOT NULL
            AND expiry IS NOT NULL
            AND contracts IS NOT NULL
            AND contracts > 0)
    )
);

CREATE INDEX IF NOT EXISTS ix_legs_cycle      ON legs(cycle_id);
CREATE INDEX IF NOT EXISTS ix_legs_status     ON legs(status);
CREATE INDEX IF NOT EXISTS ix_legs_schwab_oid ON legs(schwab_order_id);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT    NOT NULL,           -- ISO-8601 UTC
    cycle_id   INTEGER REFERENCES cycles(id) ON DELETE RESTRICT,
    leg_id     INTEGER REFERENCES legs(id)   ON DELETE RESTRICT,
    kind       TEXT    NOT NULL,           -- e.g. 'cycle_started', 'csp_sold',
                                           -- 'assigned', 'cc_sold', 'expired',
                                           -- 'called_away', 'reconciled'
    detail     TEXT                        -- JSON blob, free-form
);

CREATE INDEX IF NOT EXISTS ix_events_ts       ON events(ts);
CREATE INDEX IF NOT EXISTS ix_events_cycle    ON events(cycle_id);
"""


def apply_schema(conn: sqlite3.Connection) -> None:
    """Create tables/indexes if absent and stamp the schema version."""
    with conn:
        conn.executescript(DDL)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
