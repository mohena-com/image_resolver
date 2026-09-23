from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from .models import ImageRequest
from .resolver import resolve
from .cache import ensure_cache, cache_path

app = FastAPI(
    title="Reusable Image Resolver API",
    version="1.0.0",
    description="Resolve a named entity to a cached, reusable image."
)

ensure_cache()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/image")
def image(request: ImageRequest):
    return resolve(request.name.strip(), request.type)

@app.get("/image/{entity_type}/{name:path}")
def image_file(entity_type: str, name: str):
    result = resolve(name, entity_type)

    if result["status"] != "ok" or not result.get("local_file"):
        raise HTTPException(
            status_code=404,
            detail=result.get("error", "Image not found")
        )

    path = Path(result["local_file"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cached image disappeared")

    return FileResponse(
        path,
        media_type=result.get("media_type", "image/jpeg"),
        filename=path.name,
    )
