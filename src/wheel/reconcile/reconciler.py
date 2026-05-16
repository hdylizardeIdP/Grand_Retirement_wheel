"""Reconcile local store state against Schwab.

The reconciler is the source-of-truth bridge. It pulls current positions and
recent orders from Schwab and updates the local store to match. Every
state transition emits an event row.

Transitions we detect:

* ``open CSP`` → underlying expired worthless     → leg ``expired``
* ``open CSP`` → short put assigned, long shares  → leg ``assigned``,
                                                     SHARES leg created,
                                                     cycle state → ``holding``
* ``open CC``  → underlying expired worthless     → leg ``expired``
* ``open CC``  → shares gone, cash credited       → leg ``called_away``,
                                                     SHARES leg ``closed``,
                                                     cycle realized P&L
                                                     stamped and cycle closed
* ``open CSP`` or ``open CC`` → bought-to-close   → leg ``closed`` with the
                                                     closing order id

Idempotency: running reconcile twice produces no second event. We key off
``schwab_order_id`` and current position state, never timestamps alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from wheel.broker.client import SchwabClient
from wheel.store.db import Store


@dataclass
class ReconcileReport:
    """Summary of what reconcile did. CLI renders this as a Rich table."""

    assigned: list[int] = field(default_factory=list)        # leg ids
    called_away: list[int] = field(default_factory=list)
    expired: list[int] = field(default_factory=list)
    closed: list[int] = field(default_factory=list)
    cycles_started: list[int] = field(default_factory=list)
    cycles_closed: list[int] = field(default_factory=list)


class Reconciler:
    """Reconcile local state against the broker."""

    def __init__(self, broker: SchwabClient, store: Store) -> None:
        self._broker = broker
        self._store = store

    def reconcile(self, tickers: list[str] | None = None) -> ReconcileReport:
        """Pull state from Schwab and apply transitions to the store.

        If ``tickers`` is given, only those are reconciled; otherwise reconcile
        every ticker with an open cycle.
        """
        raise NotImplementedError
