"""
Commons is intentionally a fallback provider.

The service does not depend on Commons being reachable. If its HTTPS
endpoint is unavailable, the resolver returns to the next strategy or
reports the failure while preserving the entity result.
"""

import requests
from ..config import REQUEST_TIMEOUT

API = "https://commons.wikimedia.org/w/api.php"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "ImageResolver/1.0 (local reusable image service)"
})

def find_image(name: str):
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": name,
        "gsrnamespace": 6,
        "gsrlimit": 5,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
    }

    r = SESSION.get(API, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()

    pages = r.json().get("query", {}).get("pages", {})
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("url")
        if url:
            return {
                "provider": "Wikimedia Commons",
                "retrieval_method": "commons_search",
                "title": page.get("title"),
                "image_url": url,
                "metadata": info.get("extmetadata", {}),
            }

    return None
