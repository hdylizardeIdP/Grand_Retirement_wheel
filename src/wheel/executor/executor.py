"""Order placement with non-negotiable safety rules.

Safety rules enforced here (not in policy, not in broker):

1. ``SellCoveredCall``: ``strike >= cost_basis``. Selling a CC below cost
   guarantees a realized loss if assigned; we never do this automatically.
2. ``SellCashSecuredPut``: ``strike * 100 * contracts <= available_cash``.
   Cash-secured means cash-secured.
3. ``contracts <= config.max_contracts``.
4. ``contracts > 0`` and the contract is not expired.

Dry-run is the default. Live mode requires ``live=True`` explicitly. Dry-run
still writes the leg row (status ``open``) so reconcile + history reflect
intent; the leg is flagged with a ``dry_run`` event so it can be filtered.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from wheel.broker.client import SchwabClient
from wheel.policy.policy import ProposedAction
from wheel.store.db import Store


class SafetyError(Exception):
    """Raised when a proposed action violates a safety rule."""


@dataclass(frozen=True)
class ExecutionResult:
    action: ProposedAction
    placed: bool                 # False for dry-run
    schwab_order_id: str | None
    leg_id: int


class Executor:
    """Validate and execute proposed actions."""

    def __init__(self, broker: SchwabClient, store: Store, *, live: bool = False) -> None:
        self._broker = broker
        self._store = store
        self._live = live

    def execute(
        self,
        action: ProposedAction,
        *,
        available_cash: Decimal,
        cost_basis: Decimal | None,
        max_contracts: int,
    ) -> ExecutionResult:
        """Validate ``action``, place the order (unless dry-run), record the leg.

        Raises:
            SafetyError: If any safety rule is violated. No order is placed
                and no leg row is written.
        """
        raise NotImplementedError

    def _validate(
        self,
        action: ProposedAction,
        *,
        available_cash: Decimal,
        cost_basis: Decimal | None,
        max_contracts: int,
    ) -> None:
        """Apply safety rules. Raises :class:`SafetyError` on violation."""
        raise NotImplementedError
