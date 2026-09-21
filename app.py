from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from auto_download import download_for_person
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

APP_VERSION = "1.1.0"

# Images downloaded by the person endpoint are stored here unless the
# WIKIMEDIA_OUTPUT_DIR environment variable is set.
OUTPUT_ROOT = Path(
    __import__("os").environ.get(
        "WIKIMEDIA_OUTPUT_DIR",
        "./downloads",
    )
).expanduser().resolve()

app = FastAPI(
    title="Wikimedia Commercial-Safe Image API",
    description=(
        "FastAPI/Uvicorn service for conservative Wikimedia Commons "
        "copyright-license screening and image download."
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
    file_title: str = Field(..., description="Exact Wikimedia Commons file title")
    output_dir: str | None = None
    allow_review_images: bool = False


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
        "person_endpoint": "/v1/person/{person_name}",
    }


@app.get("/v1/person/{person_name}")
def person_image(
    person_name: str,
    limit: int = Query(
        default=15,
        ge=1,
        le=500,
        description="Number of Commons category files to inspect.",
    ),
):
    """
    One-call workflow:

        GET /v1/person/Katrina%20Kaif

    Internally:
      category -> scan -> license filter -> rights filter ->
      metadata re-check -> download -> attribution/manifest.

    The endpoint never enables review images automatically.
    """
    try:
        result = download_for_person(
            person_name=person_name,
            output_root=OUTPUT_ROOT,
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
        # 404 means the requested person category had no automatically
        # approved image; this is not a server failure.
        if result.get("reason") == "NO_AUTOMATICALLY_APPROVED_IMAGE":
            raise HTTPException(status_code=404, detail=result)
        raise HTTPException(status_code=422, detail=result)

    return result


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
        raise HTTPException(
            status_code=404,
            detail=f"Could not find image metadata for: {file_title}",
        )

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

    output_dir = (
        Path(request.output_dir).expanduser().resolve()
        if request.output_dir
        else Path("./downloads").resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = download_image(session, info, output_dir)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not result:
        raise HTTPException(
            status_code=502,
            detail="Wikimedia image could not be downloaded.",
        )

    write_manifest([result], output_dir)
    write_attribution_files([result], output_dir)

    local_file = Path(result["local_file"])

    return {
        "success": True,
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
        "download_sha256": result.get("download_sha256"),
        "attribution_file": str(
            output_dir / f"{local_file.stem}_ATTRIBUTION.txt"
        ),
        "manifest_file": str(
            output_dir / "commons_license_manifest.json"
        ),
    }
