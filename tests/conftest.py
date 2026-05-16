"""Shared pytest fixtures.

* ``store``      — a :class:`Store` backed by a tmp-path SQLite file with schema applied.
* ``mock_broker``— a :class:`unittest.mock.MagicMock` spec'd against
                   :class:`SchwabClient` so attribute typos fail loudly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from wheel.broker.client import SchwabClient
from wheel.store.db import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    s = Store(tmp_path / "wheel.db")
    s.connect()
    return s


@pytest.fixture
def mock_broker() -> MagicMock:
    return MagicMock(spec=SchwabClient)
