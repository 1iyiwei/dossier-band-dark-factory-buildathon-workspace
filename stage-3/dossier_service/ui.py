"""The browser UI: one static shell and its assets, served from the package directory."""
from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"
_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
          ".js": "text/javascript; charset=utf-8"}


def shell() -> tuple[bytes, str]:
    return asset("index.html")


def asset(name: str) -> tuple[bytes, str] | None:
    """The bytes and content type of a static file, or None when there is no such file."""
    path = STATIC_DIR / name
    if path.parent != STATIC_DIR or path.suffix not in _TYPES or not path.is_file():
        return None
    return path.read_bytes(), _TYPES[path.suffix]
