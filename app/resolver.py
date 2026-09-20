from pathlib import Path
from .cache import get_cached, save_entry, cache_path, slugify
from .license_checker import verify_commons_metadata
from .providers import wikipedia, commons

def resolve(name: str, entity_type: str):
    cached = get_cached(name, entity_type)
    if cached:
        return {
            "status": "ok",
            "name": name,
            "type": entity_type,
            "provider": cached.get("provider", "cache"),
            "retrieval_method": cached.get("retrieval_method"),
            "image_url": cached.get("image_url"),
            "local_file": cached["local_file"],
            "media_type": cached.get("media_type", "image/jpeg"),
            "license": cached.get("license"),
            "cached": True,
        }

    errors = []

    # Primary provider: Wikipedia API + article image.
    try:
        result = wikipedia.find_image(name)
        if result:
            destination = cache_path(name, entity_type, ".jpg")
            media_type = wikipedia.download_image(result["image_url"], destination)

            entry = {
                **result,
                "local_file": str(destination),
                "media_type": media_type,
                "license": {
                    "status": "NOT_VERIFIED",
                    "name": None,
                    "source_url": result.get("article_url"),
                },
            }
            save_entry(name, entity_type, entry)
            return {
                "status": "ok",
                "name": name,
                "type": entity_type,
                **{k: entry.get(k) for k in (
                    "provider", "retrieval_method", "image_url",
                    "local_file", "media_type", "license"
                )},
                "cached": False,
            }
        errors.append("Wikipedia: article/image not found")
    except Exception as exc:
        errors.append(f"Wikipedia: {exc}")

    # Secondary provider: Commons. Failure here is non-fatal.
    try:
        result = commons.find_image(name)
        if result:
            license_info = verify_commons_metadata(result.get("metadata", {}))
            if license_info["status"] != "VERIFIED":
                errors.append("Commons: image found but license not allowed/verified")
            else:
                destination = cache_path(name, entity_type, ".jpg")
                media_type = wikipedia.download_image(result["image_url"], destination)
                entry = {
                    **result,
                    "local_file": str(destination),
                    "media_type": media_type,
                    "license": license_info,
                }
                save_entry(name, entity_type, entry)
                return {
                    "status": "ok",
                    "name": name,
                    "type": entity_type,
                    **{k: entry.get(k) for k in (
                        "provider", "retrieval_method", "image_url",
                        "local_file", "media_type", "license"
                    )},
                    "cached": False,
                }
        else:
            errors.append("Commons: no image found")
    except Exception as exc:
        errors.append(f"Commons: {exc}")

    return {
        "status": "not_found",
        "name": name,
        "type": entity_type,
        "cached": False,
        "error": " | ".join(errors),
    }
