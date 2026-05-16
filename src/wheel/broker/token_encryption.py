"""Encrypted on-disk storage for the Schwab OAuth token.

Uses Fernet (symmetric AES-128-CBC + HMAC). The key comes from the
``SCHWAB_TOKEN_ENCRYPTION_KEY`` environment variable. The token file is
written atomically (write to temp, fsync, rename) so a crash mid-write can't
leave a corrupt token on disk.

NOTE: The user will paste in a prior implementation and we'll adapt it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_token(path: Path, key: str) -> dict[str, Any]:
    """Decrypt and return the token blob at ``path``."""
    raise NotImplementedError


def save_token(path: Path, key: str, token: dict[str, Any]) -> None:
    """Encrypt ``token`` and write it atomically to ``path``."""
    raise NotImplementedError
