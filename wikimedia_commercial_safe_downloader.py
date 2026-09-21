#!/usr/bin/env python3
"""
Wikimedia Commons Commercial-Reuse Downloader
==============================================

Purpose
-------
Download Wikimedia Commons images only when the Wikimedia metadata identifies
a copyright license that permits commercial reuse and that this script can
safely automate.

DEFAULT ALLOWLIST
-----------------
- Public Domain / PD
- CC0
- CC BY (all versions detected by the license metadata)

REVIEW / REJECT
---------------
- CC BY-SA      -> REVIEW (commercial use is permitted, but ShareAlike
                    obligations may matter for derivative works)
- CC BY-ND      -> REJECT (no-derivatives conflicts with common image editing)
- Any NC        -> REJECT (non-commercial)
- GFDL          -> REVIEW/REJECT for this automated workflow because its
                    attribution/share requirements are more complicated.
- Unknown       -> REJECT

IMPORTANT
---------
This is a copyright-license filter, NOT a legal guarantee.

A Commons copyright license does not automatically clear:
- publicity/personality/model rights
- privacy rights
- trademark issues
- other jurisdiction-specific restrictions

Wikimedia explicitly warns that identifiable people can have additional
rights even when the photograph is freely licensed. Therefore, images
containing identifiable people are flagged for MANUAL_PERSONALITY_RIGHTS_REVIEW.

For a monetized/commercial Instagram channel, keep the generated manifest and
attribution files as evidence of the license information checked at download
time.

The script deliberately DOES NOT disable TLS verification automatically.
If your corporate network requires an insecure connection, you must explicitly
use --insecure for testing; do not use that mode for production evidence.

Source:
https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia/licenses
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import certifi
import requests


API_URL = "https://commons.wikimedia.org/w/api.php"
DEFAULT_CATEGORY = "Category:Katrina_Kaif"

# Replace the text in this User-Agent with your own project/contact details
# if you deploy this commercially.
HEADERS = {
    "User-Agent": (
        "WikimediaCommercialImageDownloader/2.0 "
        "(automated license-audit downloader)"
    )
}

# Explicit copyright-license allowlist.
# The classifier intentionally uses a conservative approach.
SAFE_LICENSE_PATTERNS = (
    r"^CC0(?:\s|$)",
    r"^CC0 1\.0",
    r"^Creative Commons Zero",
    r"^CC BY(?:\s|$)",
    r"^CC BY [0-9]",
    r"^Creative Commons Attribution(?:\s|$)",
)

REVIEW_LICENSE_PATTERNS = (
    r"^CC BY-SA",
    r"^Creative Commons Attribution-ShareAlike",
)

REJECT_LICENSE_PATTERNS = (
    r"NC",
    r"NonCommercial",
    r"Non-Commercial",
    r"BY-ND",
    r"NoDerivatives",
    r"No-Derivatives",
    r"All rights reserved",
    r"Fully protected",
    r"Unknown",
    r"(?i)GFDL",
)

PERSONALITY_TERMS = (
    "personality rights",
    "personality_rights",
    "publicity rights",
    "right of publicity",
    "model release",
    "identifiable person",
)

TRADEMARK_TERMS = (
    "trademark",
    "trade mark",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_html(value: Optional[str]) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def first_metadata(extmetadata: Dict, *keys: str) -> str:
    for key in keys:
        item = extmetadata.get(key)
        if isinstance(item, dict):
            value = item.get("value")
            if value:
                return clean_html(str(value))
        elif item:
            return clean_html(str(item))
    return ""


def classify_license(license_name: str) -> str:
    """
    Return one of:
      SAFE_WITH_ATTRIBUTION
      SAFE_NO_ATTRIBUTION
      REVIEW_SHAREALIKE
      REJECT
    """
    name = (license_name or "").strip()

    if not name or name.lower() == "unknown":
        return "REJECT"

    # Reject NC first so a name containing both BY and NC cannot slip through.
    if re.search(r"(?i)(NC|NonCommercial|Non-Commercial)", name):
        return "REJECT"

    # ND is deliberately rejected because common Instagram processing
    # (cropping, resizing, overlays, etc.) may constitute an adaptation.
    if re.search(r"(?i)(BY-ND|NoDerivatives|No-Derivatives)", name):
        return "REJECT"

    if re.search(r"(?i)(CC0|Creative Commons Zero|Public Domain|PD)", name):
        return "SAFE_NO_ATTRIBUTION"

    if re.search(r"(?i)(CC BY-SA|Attribution-ShareAlike)", name):
        return "REVIEW_SHAREALIKE"

    if re.search(r"(?i)(^|[^A-Za-z])CC BY(?:\s|$)|Creative Commons Attribution", name):
        return "SAFE_WITH_ATTRIBUTION"

    return "REJECT"


def create_session(insecure: bool = False) -> requests.Session:
    session = requests.Session()
    session.verify = False if insecure else certifi.where()
    return session


def get_commons_files(
    session: requests.Session,
    category: str,
    limit: int = 15,
) -> List[str]:
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": category,
        "cmtype": "file",
        "cmlimit": min(limit, 500),
        "format": "json",
    }

    response = session.get(
        API_URL,
        params=params,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    return [item["title"] for item in data["query"]["categorymembers"]]


def get_image_info(
    session: requests.Session,
    file_title: str,
) -> Optional[Dict]:
    params = {
        "action": "query",
        "titles": file_title,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|user|mime|size|sha1",
        "iilimit": "1",
        "format": "json",
    }

    response = session.get(
        API_URL,
        params=params,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    pages = response.json()["query"]["pages"]
    page = next(iter(pages.values()))

    if "imageinfo" not in page:
        return None

    info = page["imageinfo"][0]
    ext = info.get("extmetadata", {})

    license_name = first_metadata(
        ext,
        "LicenseShortName",
        "License",
    ) or "Unknown"

    license_url = first_metadata(
        ext,
        "LicenseUrl",
        "LicenseUrl",
    )

    artist = first_metadata(
        ext,
        "Artist",
        "Credit",
    )

    description = first_metadata(
        ext,
        "ImageDescription",
        "ObjectName",
    )

    # Search metadata for non-copyright warnings. This does not prove that
    # a restriction applies; it deliberately creates a manual-review flag.
    metadata_blob = json.dumps(ext, ensure_ascii=False).lower()
    description_blob = (
        f"{description} {first_metadata(ext, 'Restrictions')}"
    ).lower()
    combined = f"{metadata_blob} {description_blob}"

    personality_review = any(term in combined for term in PERSONALITY_TERMS)
    trademark_review = any(term in combined for term in TRADEMARK_TERMS)

    # File titles containing likely people are not automatically rejected,
    # because the Wikimedia metadata is the primary copyright source.
    # They are nevertheless flagged for human review.
    title_or_desc = f"{file_title} {description}".lower()
    likely_person = any(
        term in title_or_desc
        for term in (
            "portrait",
            "actor",
            "actress",
            "person",
            "people",
            "celebrity",
        )
    )

    if personality_review or likely_person:
        rights_status = "MANUAL_PERSONALITY_RIGHTS_REVIEW"
    elif trademark_review:
        rights_status = "MANUAL_TRADEMARK_REVIEW"
    else:
        rights_status = "NO_AUTOMATED_NONCOPYRIGHT_CLEARANCE"

    return {
        "title": file_title,
        "url": info.get("url"),
        "description_url": info.get("descriptionurl"),
        "license": license_name,
        "license_url": license_url,
        "license_status": classify_license(license_name),
        "author": artist or info.get("user") or "Unknown",
        "description": description,
        "mime": info.get("mime"),
        "source_sha1": info.get("sha1"),
        "source_size": info.get("size"),
        "rights_status": rights_status,
        "personality_rights_review": personality_review or likely_person,
        "trademark_review": trademark_review,
        "checked_at_utc": utc_now(),
    }


def safe_filename(title: str, extension: str = "") -> str:
    name = title.replace("File:", "", 1).strip()
    name = re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE)
    name = name.strip("._") or "commons_image"

    if extension and not name.lower().endswith(extension.lower()):
        name += extension

    return name


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_image(
    session: requests.Session,
    info: Dict,
    output_dir: Path,
) -> Optional[Dict]:
    url = info.get("url")
    if not url:
        info["download_status"] = "NOT_DOWNLOADED_NO_URL"
        return None

    response = session.get(
        url,
        headers=HEADERS,
        timeout=60,
        stream=True,
    )
    response.raise_for_status()

    content_type = (response.headers.get("Content-Type") or "").lower()

    extension_map = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/tiff": ".tif",
        "image/svg+xml": ".svg",
    }

    extension = extension_map.get(content_type, "")

    filename = safe_filename(info["title"], extension)
    destination = output_dir / filename

    # Avoid accidentally overwriting an earlier download.
    if destination.exists():
        stem = destination.stem
        suffix = destination.suffix
        counter = 2
        while True:
            candidate = output_dir / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                destination = candidate
                break
            counter += 1

    with destination.open("wb") as handle:
        for block in response.iter_content(chunk_size=1024 * 1024):
            if block:
                handle.write(block)

    info["download_status"] = "DOWNLOADED"
    info["local_file"] = str(destination)
    info["download_sha256"] = sha256_file(destination)
    info["downloaded_at_utc"] = utc_now()

    return info


def write_manifest(records: List[Dict], output_dir: Path) -> None:
    manifest_json = output_dir / "commons_license_manifest.json"
    manifest_json.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    fields = [
        "title",
        "local_file",
        "license",
        "license_status",
        "license_url",
        "author",
        "description_url",
        "rights_status",
        "personality_rights_review",
        "trademark_review",
        "checked_at_utc",
        "downloaded_at_utc",
        "download_sha256",
        "source_sha1",
    ]

    with (output_dir / "commons_license_manifest.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})


def write_attribution_files(records: List[Dict], output_dir: Path) -> None:
    for record in records:
        if record.get("download_status") != "DOWNLOADED":
            continue

        local_file = Path(record["local_file"])
        attribution = (
            f"Source: Wikimedia Commons\n"
            f"File: {record['title']}\n"
            f"Author/Credit: {record.get('author') or 'Unknown'}\n"
            f"License: {record.get('license') or 'Unknown'}\n"
            f"License URL: {record.get('license_url') or 'Not supplied'}\n"
            f"Original file page: {record.get('description_url') or 'Not supplied'}\n"
            f"License checked (UTC): {record.get('checked_at_utc')}\n"
            f"Downloaded (UTC): {record.get('downloaded_at_utc')}\n"
            f"SHA-256 of downloaded file: {record.get('download_sha256')}\n"
            f"Non-copyright status: {record.get('rights_status')}\n"
            f"\n"
            f"IMPORTANT: This record documents the Wikimedia copyright-license\n"
            f"metadata found at download time. It does not establish publicity,\n"
            f"personality, privacy, trademark, model-release, or other rights.\n"
        )

        attribution_path = output_dir / f"{local_file.stem}_ATTRIBUTION.txt"
        attribution_path.write_text(attribution, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Conservative Wikimedia Commons commercial-use downloader"
    )
    parser.add_argument(
        "--category",
        default=DEFAULT_CATEGORY,
        help=f"Commons category, default: {DEFAULT_CATEGORY}",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help="Number of category files to inspect (default: 15)",
    )
    parser.add_argument(
        "--output",
        default="commons_downloads",
        help="Output directory (default: commons_downloads)",
    )
    parser.add_argument(
        "--allow-review-images",
        action="store_true",
        help=(
            "Download CC BY-SA images despite ShareAlike review and/or "
            "identifiable-person warnings. These remain flagged in the manifest."
        ),
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help=(
            "Disable TLS certificate verification. TESTING ONLY. "
            "Do not use for production/legal evidence."
        ),
    )
    args = parser.parse_args()

    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Commons category : {args.category}")
    print(f"Output directory : {output_dir}")
    print("Copyright policy  : conservative allowlist")
    print()

    session = create_session(insecure=args.insecure)

    try:
        files = get_commons_files(session, args.category, args.limit)
    except requests.RequestException as exc:
        print(f"ERROR: Could not query Wikimedia Commons: {exc}", file=sys.stderr)
        return 2

    print(f"Found {len(files)} candidate file(s).")
    print()

    records: List[Dict] = []
    downloaded = 0

    for file_title in files:
        try:
            info = get_image_info(session, file_title)
        except requests.RequestException as exc:
            print(f"[ERROR] {file_title}: metadata request failed: {exc}")
            continue

        if not info:
            print(f"[SKIP] {file_title}: no image metadata")
            continue

        status = info["license_status"]
        rights = info["rights_status"]

        print(
            f"[CHECK] {file_title}\n"
            f"        License : {info['license']}\n"
            f"        Status  : {status}\n"
            f"        Rights  : {rights}"
        )

        # Only the explicit copyright-safe allowlist is automatically
        # downloadable. CC BY-SA is allowed only with --allow-review-images.
        copyright_ok = status in {
            "SAFE_WITH_ATTRIBUTION",
            "SAFE_NO_ATTRIBUTION",
        }

        if status == "REVIEW_SHAREALIKE" and args.allow_review_images:
            copyright_ok = True

        if not copyright_ok:
            info["download_status"] = "NOT_DOWNLOADED_LICENSE_NOT_ALLOWED"
            records.append(info)
            print("        -> NOT DOWNLOADED")
            print()
            continue

        # For identifiable people, default is to stop automatic download.
        # The explicit flag means the user has consciously accepted the
        # manual-rights-review workflow.
        if info["personality_rights_review"] and not args.allow_review_images:
            info["download_status"] = (
                "NOT_DOWNLOADED_PERSONALITY_RIGHTS_REVIEW_REQUIRED"
            )
            records.append(info)
            print("        -> NOT DOWNLOADED: manual personality-rights review")
            print()
            continue

        try:
            downloaded_info = download_image(session, info, output_dir)
        except requests.RequestException as exc:
            info["download_status"] = f"DOWNLOAD_FAILED: {exc}"
            records.append(info)
            print(f"        -> DOWNLOAD FAILED: {exc}")
            print()
            continue

        if downloaded_info:
            records.append(downloaded_info)
            downloaded += 1
            print(f"        -> DOWNLOADED: {downloaded_info['local_file']}")
            print()

    write_manifest(records, output_dir)
    write_attribution_files(records, output_dir)

    print("========================================")
    print(f"Downloaded: {downloaded}")
    print(f"Manifest  : {output_dir / 'commons_license_manifest.json'}")
    print(f"CSV       : {output_dir / 'commons_license_manifest.csv'}")
    print("========================================")
    print()
    print("LEGAL/RIGHTS NOTE:")
    print(
        "This tool reduces copyright-license risk by using an explicit "
        "allowlist and preserving license evidence."
    )
    print(
        "It does NOT guarantee that an image is legally cleared for every "
        "commercial use. Identifiable people and trademarks can create "
        "separate rights issues."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
