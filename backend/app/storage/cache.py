"""Local file cache for immutable objects (Parquet versions, split files).

Versions never change after they are written (rule 1), so a cached copy is always valid.
"""

import hashlib
from pathlib import Path

import pandas as pd

from app.core.config import get_settings
from app.storage.backend import get_storage


def local_path(storage_key: str) -> Path:
    """Download `storage_key` once and return the local path."""
    digest = hashlib.sha256(storage_key.encode()).hexdigest()[:32]
    suffix = Path(storage_key).suffix or ".bin"
    path = Path(get_settings().cache_dir) / f"{digest}{suffix}"
    if not path.exists():
        get_storage().download(storage_key, path)
    return path


def read_parquet(storage_key: str, columns: list[str] | None = None) -> pd.DataFrame:
    return pd.read_parquet(local_path(storage_key), columns=columns)
