import json
import re
from pathlib import Path
from .config import CACHE_ROOT, TYPE_DIRS

INDEX_FILE = CACHE_ROOT / "index.json"

def slugify(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[-\s]+", "_", value.strip().lower())
    return value[:120] or "unknown"

def ensure_cache():
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    for folder in TYPE_DIRS.values():
        (CACHE_ROOT / folder).mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text("{}", encoding="utf-8")

def cache_path(name: str, entity_type: str, extension: str = ".jpg") -> Path:
    folder = CACHE_ROOT / TYPE_DIRS.get(entity_type, "other")
    return folder / f"{slugify(name)}{extension}"

def read_index() -> dict:
    ensure_cache()
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_index(data: dict):
    ensure_cache()
    tmp = INDEX_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(INDEX_FILE)

def get_cached(name: str, entity_type: str):
    data = read_index()
    key = f"{entity_type}:{name.strip().lower()}"
    entry = data.get(key)
    if entry:
        path = Path(entry.get("local_file", ""))
        if path.exists():
            return entry
    path = cache_path(name, entity_type)
    if path.exists():
        return {"local_file": str(path), "cached": True}
    return None

def save_entry(name: str, entity_type: str, entry: dict):
    data = read_index()
    key = f"{entity_type}:{name.strip().lower()}"
    data[key] = entry
    write_index(data)
