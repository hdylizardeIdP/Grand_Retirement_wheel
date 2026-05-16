"""Policy decision tests.

The policy module is pure: feed it a cycle, a config, and a synthetic chain,
assert the returned action. No broker, no DB.

Cases to cover:

* ``no_shares`` cycle, healthy chain → returns a ``SellCashSecuredPut`` for
  the contract closest to ``target_delta`` within the DTE window.
* ``holding`` cycle, healthy chain → returns a ``SellCoveredCall``.
* Chain is empty or every credit is below ``min_credit`` → returns ``None``.
* Disabled ticker → returns ``None``.
* Open opposite-leg already exists → returns ``None`` (don't stack).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="policy not yet implemented")


def test_no_shares_picks_target_delta_csp() -> None:
    raise NotImplementedError


def test_holding_picks_target_delta_cc() -> None:
    raise NotImplementedError


def test_empty_chain_returns_none() -> None:
    raise NotImplementedError


def test_credit_floor_returns_none() -> None:
    raise NotImplementedError


def test_disabled_ticker_returns_none() -> None:
    raise NotImplementedError


def test_open_leg_blocks_new_action() -> None:
    raise NotImplementedError
