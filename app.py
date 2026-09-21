from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from wikimedia_commercial_safe_downloader import (
    DEFAULT_CATEGORY,
    classify_license,
    create_session,
    download_image,
    get_commons_files,
    get_image_info,
    write_attribution_files,
    write_manifest,
)

APP_VERSION = "1.0.0"

app = FastAPI(
    title="Wikimedia Commercial-Safe Image API",
    description=(
        "Uvicorn/FastAPI service around a conservative Wikimedia Commons "
        "copyright-license filter."
    ),
    version=APP_VERSION,
)


class ScanRequest(BaseModel):
    category: str = Field(
        default=DEFAULT_CATEGORY,
        description="Wikimedia Commons category, e.g. Category:Katrina_Kaif",
    )
    limit: int = Field(default=15, ge=1, le=500)


class DownloadRequest(BaseModel):
    file_title: str = Field(
        ...,
        description="Exact Wikimedia Commons file title, e.g. File:Example.jpg",
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="Optional server-side output directory.",
    )
    allow_review_images: bool = Field(
        default=False,
        description=(
            "Allow CC BY-SA or images requiring personality-rights review. "
            "Use only when you will manually review the result."
        ),
    )


def get_info_or_404(file_title: str):
    session = create_session()
    try:
        info = get_image_info(session, file_title)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not info:
        raise HTTPException(
            status_code=404,
            detail=f"Could not find image metadata for: {file_title}",
        )
    return session, info


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "wikimedia-commercial-safe-image-api",
        "version": APP_VERSION,
    }


@app.get("/")
def root():
    return {
        "service": "Wikimedia Commercial-Safe Image API",
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


@app.post("/v1/scan")
def scan(request: ScanRequest):
    """
    Scan a Commons category and classify every candidate.

    This endpoint does NOT download files.
    """
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
    """
    Return Wikimedia metadata and the automated copyright/right-status
    classification without downloading the image.
    """
    _, info = get_info_or_404(file_title)
    return info


@app.post("/v1/image/download")
def image_download(request: DownloadRequest):
    """
    Download exactly one Wikimedia file after applying the conservative
    license filter.

    Default policy:
      SAFE_WITH_ATTRIBUTION
      SAFE_NO_ATTRIBUTION

    CC BY-SA and identifiable-person cases require explicit
    allow_review_images=true.
    """
    session, info = get_info_or_404(request.file_title)

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
                "message": "Image rejected by the copyright-license policy.",
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
                "message": (
                    "Image requires manual personality/publicity-rights "
                    "review before download."
                ),
                "rights_status": info.get("rights_status"),
                "file_title": request.file_title,
            },
        )

    if request.output_dir:
        output_dir = Path(request.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = Path(tempfile.mkdtemp(prefix="wikimedia_api_"))

    try:
        result = download_image(session, info, output_dir)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not result:
        raise HTTPException(
            status_code=502,
            detail="Wikimedia image could not be downloaded.",
        )

    # Persist a machine-readable audit trail alongside the image.
    write_manifest([result], output_dir)
    write_attribution_files([result], output_dir)

    return {
        "success": True,
        "file": result.get("local_file"),
        "license": result.get("license"),
        "license_status": result.get("license_status"),
        "license_url": result.get("license_url"),
        "author": result.get("author"),
        "description_url": result.get("description_url"),
        "rights_status": result.get("rights_status"),
        "personality_rights_review": result.get(
            "personality_rights_review"
        ),
        "download_sha256": result.get("download_sha256"),
        "attribution_file": str(
            output_dir
            / f"{Path(result['local_file']).stem}_ATTRIBUTION.txt"
        ),
        "manifest_file": str(
            output_dir / "commons_license_manifest.json"
        ),
    }
