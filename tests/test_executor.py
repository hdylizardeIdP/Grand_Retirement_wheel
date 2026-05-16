"""Executor safety-rule tests.

Cases to cover:

* Dry-run by default: ``place_order`` is not called; a leg row is still written.
* Live mode: ``place_order`` is called with the action's order spec and the
  returned Schwab order id is stored on the leg.
* CC with strike < cost basis → ``SafetyError``; no order, no leg.
* CSP whose collateral exceeds available cash → ``SafetyError``.
* Contracts > ``max_contracts`` → ``SafetyError``.
* Zero / negative contracts → ``SafetyError``.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="executor not yet implemented")


def test_dry_run_does_not_place_order_but_writes_leg() -> None:
    raise NotImplementedError


def test_live_mode_places_order_and_records_order_id() -> None:
    raise NotImplementedError


def test_cc_below_cost_basis_rejected() -> None:
    raise NotImplementedError


def test_csp_collateral_exceeds_cash_rejected() -> None:
    raise NotImplementedError


def test_contracts_above_cap_rejected() -> None:
    raise NotImplementedError


def test_non_positive_contracts_rejected() -> None:
    raise NotImplementedError
