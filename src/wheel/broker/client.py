"""Schwab API client wrapper.

Wraps ``schwab-py`` with the narrow surface this bot needs. Token I/O is
delegated to :mod:`wheel.broker.token_encryption` so the on-disk token is
always encrypted at rest.

NOTE: The user will paste in a ``client.py`` and ``token_encryption.py`` from
a prior project and we'll adapt them. This file is a placeholder describing
the intended public interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class Quote:
    """Snapshot quote for a symbol."""

    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal


@dataclass(frozen=True)
class OptionContract:
    """One option contract within a chain."""

    symbol: str            # OCC-style option symbol used by Schwab
    underlying: str
    expiry: date
    strike: Decimal
    option_type: str       # "PUT" or "CALL"
    bid: Decimal
    ask: Decimal
    delta: float | None
    open_interest: int
    volume: int


class SchwabClient:
    """Narrow Schwab client used by the wheel bot.

    Construct via :meth:`from_settings`; the constructor handles OAuth token
    load/refresh through the encrypted token store.
    """

    def __init__(self, *, account_hash: str, raw_client: Any) -> None:
        self._account_hash = account_hash
        self._client = raw_client

    @classmethod
    def from_settings(cls, settings: Any) -> SchwabClient:
        """Build a client from :class:`wheel.config.Settings`."""
        raise NotImplementedError

    # --- account state -----------------------------------------------------

    def get_positions(self) -> list[dict[str, Any]]:
        """Current positions for the configured account."""
        raise NotImplementedError

    def get_balances(self) -> dict[str, Any]:
        """Current cash and buying-power balances."""
        raise NotImplementedError

    # --- market data -------------------------------------------------------

    def get_quote(self, symbol: str) -> Quote:
        """Single-symbol quote."""
        raise NotImplementedError

    def get_option_chain(
        self,
        underlying: str,
        *,
        option_type: str,
        dte_min: int,
        dte_max: int,
    ) -> list[OptionContract]:
        """Filtered option chain for ``underlying``.

        ``option_type`` is ``"PUT"`` or ``"CALL"``. Returns contracts whose
        expiry falls within ``[today + dte_min, today + dte_max]``.
        """
        raise NotImplementedError

    # --- orders ------------------------------------------------------------

    def get_orders(self, *, from_entered_time: Any = None) -> list[dict[str, Any]]:
        """Order history for the configured account."""
        raise NotImplementedError

    def get_order(self, order_id: str) -> dict[str, Any]:
        """Single order by Schwab order id."""
        raise NotImplementedError

    def place_order(self, order_spec: dict[str, Any]) -> str:
        """Place an order. Returns the Schwab order id.

        Caller is responsible for constructing ``order_spec`` (typically via
        ``schwab.orders.options`` helpers). This wrapper does no validation;
        :mod:`wheel.executor` is the guardrail layer.
        """
        raise NotImplementedError
