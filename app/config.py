from pathlib import Path
import os

CACHE_ROOT = Path(os.getenv("IMAGE_CACHE_ROOT", "/Volumes/Extreme SSD/webmaster-ai/POJO_PROJECT/data/images")).resolve()
WIKIPEDIA_API = os.getenv("WIKIPEDIA_API", "https://en.wikipedia.org/w/api.php")
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "15"))
MAX_DOWNLOAD_BYTES = int(os.getenv("MAX_DOWNLOAD_BYTES", str(15 * 1024 * 1024)))

ALLOWED_LICENSES = {
    "public domain",
    "cc0",
    "cc by 4.0",
    "cc by 3.0",
    "cc by 2.0",
}

TYPE_DIRS = {
    "person": "people",
    "movie": "movies",
    "tv_show": "shows",
    "place": "places",
    "organization": "organizations",
    "event": "events",
    "other": "other",
}
