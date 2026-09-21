"""
Internal helper for the Wikimedia FastAPI service.

The public API should call download_for_person() rather than exposing the
scan/info/download sequence to API clients.

The helper:
    1. Converts a person name into a Wikimedia Commons category candidate.
    2. Scans category files.
    3. Applies the conservative copyright/right filters.
    4. Re-checks the selected file's metadata.
    5. Downloads the approved image.
    6. Writes attribution and manifest evidence.

This helper intentionally does NOT download images that require manual
personality/publicity-rights review.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional

from wikimedia_commercial_safe_downloader import (
    create_session,
    download_image,
    get_commons_files,
    get_image_info,
    write_attribution_files,
    write_manifest,
)


def person_to_category(person_name: str) -> str:
    """
    Convert a person name into the conventional Wikimedia Commons category
    form.

    Example:
        Katrina Kaif -> Category:Katrina_Kaif
    """
    name = " ".join(person_name.strip().split())

    if not name:
        raise ValueError("Person name cannot be empty.")

    # Preserve Unicode names, remove characters that are inappropriate for
    # a Commons category title, and convert spaces to underscores.
    name = re.sub(r"[\r\n\t]+", " ", name)
    name = re.sub(r"[\[\]{}<>|]+", "", name)
    name = re.sub(r"\s+", " ", name).strip()

    return "Category:" + name.replace(" ", "_")


def is_automatically_approved(info: Dict) -> bool:
    """
    Strict automatic approval gate.

    A file must:
      - have an explicitly allowed copyright license;
      - not have a personality-rights review flag;
      - not have a trademark review flag;
      - have no other automated non-copyright clearance warning.
    """
    return (
        info.get("license_status")
        in {
            "SAFE_WITH_ATTRIBUTION",
            "SAFE_NO_ATTRIBUTION",
        }
        and not info.get("personality_rights_review", False)
        and not info.get("trademark_review", False)
        and info.get("rights_status")
        == "NO_AUTOMATED_NONCOPYRIGHT_CLEARANCE"
    )


def download_for_person(
    person_name: str,
    output_root: str | Path,
    limit: int = 15,
) -> Dict:
    """
    Find and download the first automatically approved Wikimedia Commons
    image for a person.

    Returns a JSON-serializable dictionary suitable for a FastAPI response.
    """
    person_name = " ".join(person_name.strip().split())

    if not person_name:
        raise ValueError("Person name cannot be empty.")

    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500.")

    category = person_to_category(person_name)
    session = create_session()

    files = get_commons_files(
        session,
        category,
        limit,
    )

    candidates = []
    selected = None

    for file_title in files:
        try:
            info = get_image_info(session, file_title)
        except Exception as exc:
            candidates.append(
                {
                    "title": file_title,
                    "license_status": "ERROR",
                    "error": str(exc),
                }
            )
            continue

        if not info:
            continue

        candidates.append(
            {
                "title": info.get("title"),
                "license": info.get("license"),
                "license_status": info.get("license_status"),
                "rights_status": info.get("rights_status"),
                "personality_rights_review": info.get(
                    "personality_rights_review"
                ),
                "trademark_review": info.get("trademark_review"),
                "description_url": info.get("description_url"),
            }
        )

        if selected is None and is_automatically_approved(info):
            selected = info

    if selected is None:
        return {
            "success": False,
            "person": person_name,
            "category": category,
            "reason": "NO_AUTOMATICALLY_APPROVED_IMAGE",
            "candidates_checked": len(candidates),
            "candidates": candidates,
        }

    # Re-fetch metadata immediately before download.
    verified = get_image_info(session, selected["title"])

    if not verified or not is_automatically_approved(verified):
        return {
            "success": False,
            "person": person_name,
            "category": category,
            "reason": "FAILED_FINAL_RIGHTS_RECHECK",
            "file_title": selected["title"],
        }

    person_dir = (
        Path(output_root).expanduser().resolve()
        / re.sub(r"[^\w.-]+", "_", person_name, flags=re.UNICODE).strip("_")
    )
    person_dir.mkdir(parents=True, exist_ok=True)

    result = download_image(
        session,
        verified,
        person_dir,
    )

    if not result:
        return {
            "success": False,
            "person": person_name,
            "category": category,
            "reason": "DOWNLOAD_FAILED",
            "file_title": verified["title"],
        }

    write_manifest([result], person_dir)
    write_attribution_files([result], person_dir)

    local_file = Path(result["local_file"])

    return {
        "success": True,
        "person": person_name,
        "category": category,
        "file_title": result.get("title"),
        "file": str(local_file),
        "license": result.get("license"),
        "license_status": result.get("license_status"),
        "license_url": result.get("license_url"),
        "author": result.get("author"),
        "description_url": result.get("description_url"),
        "rights_status": result.get("rights_status"),
        "personality_rights_review": result.get(
            "personality_rights_review"
        ),
        "trademark_review": result.get("trademark_review"),
        "download_sha256": result.get("download_sha256"),
        "attribution_file": str(
            person_dir / f"{local_file.stem}_ATTRIBUTION.txt"
        ),
        "manifest_file": str(
            person_dir / "commons_license_manifest.json"
        ),
        "candidates_checked": len(candidates),
    }
