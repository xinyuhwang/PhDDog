"""Local file storage under DATA_DIR. Swap for S3 later behind the same functions."""

import hashlib
from pathlib import Path

from app.config import get_settings


def data_path(*parts: str) -> Path:
    path = get_settings().data_dir.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_bytes(content: bytes, *parts: str) -> str:
    path = data_path(*parts)
    path.write_bytes(content)
    return str(path)


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
