"""Thin Schwab API wrapper.

Intentionally Schwab-specific. No broker-agnostic interface; if we ever need
another broker we'll add it then.
"""

from wheel.broker.client import SchwabClient

__all__ = ["SchwabClient"]
