"""Reconciliation transition tests.

Each test sets up the local store in a known state, stubs the broker's
``get_positions`` / ``get_orders`` return values, runs the reconciler, and
asserts both (a) the resulting store state and (b) that the corresponding
event was recorded.

Cases to cover:

* CSP expires worthless → leg ``expired``, cycle still ``no_shares``.
* CSP assigned → leg ``assigned``, SHARES leg created, cycle ``holding``.
* CC expires worthless → leg ``expired``, cycle still ``holding``.
* CC called away → leg ``called_away``, SHARES leg closed, cycle ended,
  realized P&L = sum of premiums + (strike - cost_basis) * 100 - fees.
* Bought-to-close (closing order present) → leg ``closed``.
* Idempotency: running reconcile twice produces exactly one event each.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="reconciler not yet implemented")


def test_csp_expires_worthless() -> None:
    raise NotImplementedError


def test_csp_assigned_transitions_to_holding() -> None:
    raise NotImplementedError


def test_cc_expires_worthless() -> None:
    raise NotImplementedError


def test_cc_called_away_closes_cycle() -> None:
    raise NotImplementedError


def test_bought_to_close_marks_leg_closed() -> None:
    raise NotImplementedError


def test_reconcile_is_idempotent() -> None:
    raise NotImplementedError
