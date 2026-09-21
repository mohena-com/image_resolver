from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from auto_download import download_for_person
from cache import DEFAULT_CACHE_ROOT, find_cached, slugify, store
from wikimedia_commercial_safe_downloader import (
    DEFAULT_CATEGORY,
    create_session,
    download_image,
    get_commons_files,
    get_image_info,
    write_attribution_files,
    write_manifest,
)

APP_VERSION = "1.2.0"

OUTPUT_ROOT = Path(
    os.environ.get(
        "WIKIMEDIA_IMAGE_CACHE",
        str(DEFAULT_CACHE_ROOT),
    )
).expanduser().resolve()

app = FastAPI(
    title="Wikimedia Commercial-Safe Image API",
    description=(
        "FastAPI/Uvicorn service for conservative Wikimedia Commons "
        "copyright-license screening, download and local image caching."
    ),
    version=APP_VERSION,
)


class ScanRequest(BaseModel):
    category: str = Field(default=DEFAULT_CATEGORY)
    limit: int = Field(default=15, ge=1, le=500)


class DownloadRequest(BaseModel):
    file_title: str
    output_dir: str | None = None
    allow_review_images: bool = False


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "wikimedia-commercial-safe-image-api",
        "version": APP_VERSION,
        "cache_root": str(OUTPUT_ROOT),
    }


@app.get("/")
def root():
    return {
        "service": "Wikimedia Commercial-Safe Image API",
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/health",
        "person_endpoint": "/v1/person/{person_name}",
        "cache_root": str(OUTPUT_ROOT),
    }


@app.get("/v1/person/{person_name}")
def person_image(
    person_name: str,
    limit: int = Query(default=15, ge=1, le=500),
):
    """
    One-call person lookup with local cache.

    First hit:
        local cache -> MISS -> Wikimedia scan -> approved image download
        -> people/<person>.jpg -> index.json

    Second/subsequent hit:
        local cache -> HIT -> return existing image
        (no Wikimedia API call and no second download)
    """
    person_name = " ".join(person_name.strip().split())

    if not person_name:
        raise HTTPException(status_code=400, detail="Person name is required.")

    # IMPORTANT: people is the corresponding cache folder for this endpoint.
    cached = find_cached(
        name=person_name,
        category="people",
        cache_root=OUTPUT_ROOT,
    )

    if cached:
        return {
            "success": True,
            "cache_hit": True,
            "person": person_name,
            "category": "people",
            "file": cached["file"],
            "file_title": cached.get("file_title"),
            "license": cached.get("license"),
            "license_status": cached.get("license_status"),
            "license_url": cached.get("license_url"),
            "author": cached.get("author"),
            "description_url": cached.get("description_url"),
            "rights_status": cached.get("rights_status"),
            "download_sha256": cached.get("download_sha256"),
            "attribution_file": cached.get("attribution_file"),
            "manifest_file": cached.get("manifest_file"),
            "cached_at_utc": cached.get("cached_at_utc"),
        }

    try:
        result = download_for_person(
            person_name=person_name,
            output_root=OUTPUT_ROOT / "people",
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Wikimedia lookup/download failed: {exc}",
        ) from exc

    if not result.get("success"):
        if result.get("reason") == "NO_AUTOMATICALLY_APPROVED_IMAGE":
            raise HTTPException(status_code=404, detail=result)
        raise HTTPException(status_code=422, detail=result)

    # Persist one canonical index record.
    file_path = result["file"]
    attribution_file = result.get("attribution_file")
    manifest_file = result.get("manifest_file")

    record = store(
        name=person_name,
        category="people",
        file_path=file_path,
        metadata={
            "file_title": result.get("file_title"),
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
            "attribution_file": attribution_file,
            "manifest_file": manifest_file,
            "candidates_checked": result.get("candidates_checked"),
        },
        cache_root=OUTPUT_ROOT,
    )

    return {
        **result,
        "cache_hit": False,
        "category": "people",
        "cached_at_utc": record.get("cached_at_utc"),
    }


@app.post("/v1/scan")
def scan(request: ScanRequest):
    session = create_session()

    try:
        files = get_commons_files(
            session,
            request.category,
            request.limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    results = []

    for file_title in files:
        try:
            info = get_image_info(session, file_title)
            if info:
                results.append(info)
        except Exception as exc:
            results.append(
                {
                    "title": file_title,
                    "license_status": "ERROR",
                    "error": str(exc),
                }
            )

    return {
        "category": request.category,
        "count": len(results),
        "results": results,
    }


@app.get("/v1/image/info")
def image_info(file_title: str):
    session = create_session()

    try:
        info = get_image_info(session, file_title)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not info:
        raise HTTPException(status_code=404, detail="Image not found.")

    return info


@app.post("/v1/image/download")
def image_download(request: DownloadRequest):
    session = create_session()

    try:
        info = get_image_info(session, request.file_title)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not info:
        raise HTTPException(status_code=404, detail="Image not found.")

    status = info["license_status"]
    copyright_ok = status in {
        "SAFE_WITH_ATTRIBUTION",
        "SAFE_NO_ATTRIBUTION",
    }

    if status == "REVIEW_SHAREALIKE" and request.allow_review_images:
        copyright_ok = True

    if not copyright_ok:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Image rejected by copyright-license policy.",
                "license": info.get("license"),
                "license_status": status,
                "file_title": request.file_title,
            },
        )

    if (
        info.get("personality_rights_review")
        and not request.allow_review_images
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Manual personality/publicity-rights review required.",
                "rights_status": info.get("rights_status"),
                "file_title": request.file_title,
            },
        )

    output_dir = (
        Path(request.output_dir).expanduser().resolve()
        if request.output_dir
        else OUTPUT_ROOT / "other"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = download_image(session, info, output_dir)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not result:
        raise HTTPException(status_code=502, detail="Download failed.")

    write_manifest([result], output_dir)
    write_attribution_files([result], output_dir)

    local_file = Path(result["local_file"])

    return {
        "success": True,
        "cache_hit": False,
        "file": str(local_file),
        "license": result.get("license"),
        "license_status": result.get("license_status"),
        "license_url": result.get("license_url"),
        "author": result.get("author"),
        "description_url": result.get("description_url"),
        "rights_status": result.get("rights_status"),
        "download_sha256": result.get("download_sha256"),
        "attribution_file": str(
            output_dir / f"{local_file.stem}_ATTRIBUTION.txt"
        ),
        "manifest_file": str(
            output_dir / "commons_license_manifest.json"
        ),
    }
