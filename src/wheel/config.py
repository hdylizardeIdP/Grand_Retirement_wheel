"""Configuration loading.

Two layers:

* Process-level settings from environment / .env (paths, credentials, log level).
  Exposed as :class:`Settings`.
* Per-ticker strategy parameters from a YAML file (target delta, DTE range,
  credit floor, contracts cap, enabled flag). Exposed as :class:`TickerConfig`
  and loaded by :func:`load_ticker_configs`.

Keep this module dependency-light: no broker imports, no DB imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Process-level settings read from the environment."""

    schwab_app_key: str
    schwab_app_secret: str
    schwab_callback_url: str
    schwab_account_hash: str
    schwab_token_path: Path
    schwab_token_encryption_key: str
    db_path: Path
    tickers_path: Path
    log_level: str


@dataclass(frozen=True)
class TickerConfig:
    """Per-ticker wheel parameters."""

    ticker: str
    enabled: bool
    target_delta: float
    dte_min: int
    dte_max: int
    min_credit: float
    max_contracts: int


def load_settings() -> Settings:
    """Read environment (and .env if present) and return :class:`Settings`.

    Raises a clear error if required values are missing.
    """
    raise NotImplementedError


def load_ticker_configs(path: Path) -> dict[str, TickerConfig]:
    """Load and validate the per-ticker YAML config.

    Merges ``defaults:`` into each entry under ``tickers:``. Returns a mapping
    of ticker symbol → :class:`TickerConfig`.
    """
    raise NotImplementedError
