import re
import requests
from urllib.parse import quote
from ..config import WIKIPEDIA_API, REQUEST_TIMEOUT, MAX_DOWNLOAD_BYTES

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "ImageResolver/1.0 (local reusable image service)"
})

def _search_article(name: str):
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": name,
        "srnamespace": 0,
        "srlimit": 5,
    }
    r = SESSION.get(WIKIPEDIA_API, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    results = r.json().get("query", {}).get("search", [])
    if not results:
        return None

    exact = name.strip().casefold()
    for item in results:
        if item.get("title", "").casefold() == exact:
            return item["title"]
    return results[0].get("title")

def find_image(name: str):
    title = _search_article(name)
    if not title:
        return None

    params = {
        "action": "query",
        "format": "json",
        "prop": "pageimages|info",
        "piprop": "original",
        "inprop": "url",
        "titles": title,
        "redirects": 1,
    }
    r = SESSION.get(WIKIPEDIA_API, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    original = page.get("original") or {}
    source = original.get("source")
    if not source:
        return None

    return {
        "provider": "Wikipedia",
        "retrieval_method": "wikipedia_article",
        "title": page.get("title", title),
        "image_url": source,
        "article_url": page.get("fullurl"),
    }

def download_image(url: str, destination):
    with SESSION.get(
        url,
        timeout=REQUEST_TIMEOUT,
        stream=True,
        allow_redirects=True,
    ) as r:
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "").lower()
        if not content_type.startswith("image/"):
            raise ValueError(f"URL did not return an image: {content_type}")

        length = r.headers.get("Content-Length")
        if length and int(length) > MAX_DOWNLOAD_BYTES:
            raise ValueError("Image exceeds maximum download size")

        written = 0
        with open(destination, "wb") as f:
            for chunk in r.iter_content(64 * 1024):
                if not chunk:
                    continue
                written += len(chunk)
                if written > MAX_DOWNLOAD_BYTES:
                    raise ValueError("Image exceeds maximum download size")
                f.write(chunk)

        return content_type
