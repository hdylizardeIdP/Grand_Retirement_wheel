"""``wheel`` command-line interface.

Subcommands:

* ``wheel status``                — open cycles, open legs, balances. Rich table.
* ``wheel reconcile``             — pull Schwab state, update store, print report.
* ``wheel tick <ticker>``         — reconcile → policy → executor for one ticker.
* ``wheel tick-all``              — same, for every enabled ticker.
* ``wheel history <ticker>``      — closed cycles and event log for a ticker.

Dry-run is the default for ``tick`` / ``tick-all``. Pass ``--live`` to place
real orders.
"""

from __future__ import annotations

import click


@click.group()
@click.version_option()
def cli() -> None:
    """Wheel options strategy bot."""


@cli.command()
def status() -> None:
    """Show open cycles, open legs, and account balances."""
    raise NotImplementedError


@cli.command()
def reconcile() -> None:
    """Pull state from Schwab and update the local store."""
    raise NotImplementedError


@cli.command()
@click.argument("ticker")
@click.option("--live", is_flag=True, default=False, help="Place real orders (default: dry-run).")
def tick(ticker: str, live: bool) -> None:
    """Run reconcile → policy → executor for a single ticker."""
    raise NotImplementedError


@cli.command("tick-all")
@click.option("--live", is_flag=True, default=False, help="Place real orders (default: dry-run).")
def tick_all(live: bool) -> None:
    """Run the tick loop for every enabled ticker."""
    raise NotImplementedError


@cli.command()
@click.argument("ticker")
def history(ticker: str) -> None:
    """Show closed cycles and event log for a ticker."""
    raise NotImplementedError


if __name__ == "__main__":
    cli()
