"""
Local image cache for the Wikimedia API.

Cache layout:

data/images/
├── people/
├── movies/
├── shows/
├── places/
├── organizations/
├── events/
├── other/
└── index.json

A cache hit is returned without contacting Wikimedia Commons.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DEFAULT_CACHE_ROOT = Path(
    __import__("os").environ.get(
        "WIKIMEDIA_IMAGE_CACHE",
        "./data/images",
    )
).expanduser().resolve()

CATEGORIES = {
    "people",
    "movies",
    "shows",
    "places",
    "organizations",
    "events",
    "other",
}


def slugify(value: str) -> str:
    value = " ".join(value.strip().split())
    value = re.sub(r"[^\w\s.-]", "", value, flags=re.UNICODE)
    value = re.sub(r"\s+", "_", value)
    return value.strip("._") or "unknown"


def category_dir(category: str, cache_root: Path) -> Path:
    category = category.lower().strip()
    if category not in CATEGORIES:
        category = "other"
    path = cache_root / category
    path.mkdir(parents=True, exist_ok=True)
    return path


def index_path(cache_root: Path) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root / "index.json"


def load_index(cache_root: Path) -> dict:
    path = index_path(cache_root)
    if not path.exists():
        return {"version": 1, "images": {}}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
        data.setdefault("version", 1)
        data.setdefault("images", {})
        return data
    except Exception:
        # Do not destroy a corrupt index. Start a fresh in-memory index;
        # the next successful write will repair it.
        return {"version": 1, "images": {}}


def save_index(cache_root: Path, data: dict) -> None:
    path = index_path(cache_root)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)


def cache_key(category: str, name: str) -> str:
    return f"{category.lower().strip()}:{slugify(name).lower()}"


def find_cached(
    name: str,
    category: str,
    cache_root: Path,
) -> Optional[dict]:
    """
    Return cached metadata only if the indexed local image still exists.
    """
    data = load_index(cache_root)
    key = cache_key(category, name)
    record = data.get("images", {}).get(key)

    if not record:
        return None

    file_path = Path(record.get("file", ""))
    if not file_path.is_absolute():
        file_path = cache_root / file_path

    if not file_path.exists() or not file_path.is_file():
        return None

    result = dict(record)
    result["file"] = str(file_path)
    result["cache_hit"] = True
    return result


def store(
    *,
    name: str,
    category: str,
    file_path: str | Path,
    metadata: dict,
    cache_root: Path,
) -> dict:
    """
    Add/update a cache record.

    file path is stored relative to the cache root so the cache can be moved
    to another machine/drive without rewriting every record.
    """
    file_path = Path(file_path).resolve()
    cache_root = cache_root.resolve()

    try:
        relative_file = str(file_path.relative_to(cache_root))
    except ValueError:
        relative_file = str(file_path)

    record = {
        "name": name,
        "category": category,
        "file": relative_file,
        "cached_at_utc": datetime.now(timezone.utc).isoformat(),
        **metadata,
        "cache_hit": False,
    }

    data = load_index(cache_root)
    data["images"][cache_key(category, name)] = record
    save_index(cache_root, data)

    result = dict(record)
    result["file"] = str(file_path)
    return result
