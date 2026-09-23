from typing import Literal, Optional
from pydantic import BaseModel, Field

EntityType = Literal[
    "person", "movie", "tv_show", "place", "organization", "event", "other"
]

class ImageRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    type: EntityType = "other"

class LicenseInfo(BaseModel):
    status: str
    name: Optional[str] = None
    source_url: Optional[str] = None

class ImageResponse(BaseModel):
    status: str
    name: str
    type: str
    provider: Optional[str] = None
    retrieval_method: Optional[str] = None
    image_url: Optional[str] = None
    local_file: Optional[str] = None
    media_type: Optional[str] = None
    license: Optional[LicenseInfo] = None
    cached: bool = False
    error: Optional[str] = None
