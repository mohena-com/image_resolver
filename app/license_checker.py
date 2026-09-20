import re
from .config import ALLOWED_LICENSES

def clean(value):
    return re.sub(r"<[^>]+>", "", value or "").strip()

def normalize_license(text):
    text = clean(text).casefold()
    if "creative commons attribution 4.0" in text or text == "cc by 4.0":
        return "CC BY 4.0"
    if "creative commons attribution 3.0" in text or text == "cc by 3.0":
        return "CC BY 3.0"
    if "creative commons attribution 2.0" in text or text == "cc by 2.0":
        return "CC BY 2.0"
    if "cc0" in text or "public domain" in text:
        return "Public Domain" if "public domain" in text else "CC0"
    return None

def verify_commons_metadata(metadata: dict):
    usage = metadata.get("LicenseShortName", {}).get("value", "")
    url = metadata.get("LicenseUrl", {}).get("value", "")
    normalized = normalize_license(usage)

    if normalized and normalized.casefold() in ALLOWED_LICENSES:
        return {
            "status": "VERIFIED",
            "name": normalized,
            "source_url": url or None,
        }

    return {
        "status": "NOT_VERIFIED",
        "name": usage or None,
        "source_url": url or None,
    }
