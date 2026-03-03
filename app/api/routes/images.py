"""Image-related API endpoints."""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.db.models import DocImage
from app.db.postgres import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


class ImageResponse(BaseModel):
    image_id: int
    doc_id: int
    page_number: Optional[int]
    image_path: str
    image_type: Optional[str]
    width: Optional[int]
    height: Optional[int]
    description: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


@router.get("/documents/{doc_id}/images", response_model=list[ImageResponse])
def list_document_images(doc_id: int):
    """문서의 모든 이미지 목록 조회."""
    with get_session() as session:
        images = (
            session.query(DocImage)
            .filter(DocImage.doc_id == doc_id)
            .order_by(DocImage.page_number, DocImage.image_id)
            .all()
        )
        return [
            ImageResponse(
                image_id=img.image_id,
                doc_id=img.doc_id,
                page_number=img.page_number,
                image_path=img.image_path,
                image_type=img.image_type,
                width=img.width,
                height=img.height,
                description=img.description,
                created_at=str(img.created_at),
            )
            for img in images
        ]


@router.get("/images/{image_id}", response_model=ImageResponse)
def get_image_metadata(image_id: int):
    """이미지 메타데이터 조회."""
    with get_session() as session:
        img = session.query(DocImage).filter(DocImage.image_id == image_id).first()
        if not img:
            raise HTTPException(status_code=404, detail="Image not found")
        return ImageResponse(
            image_id=img.image_id,
            doc_id=img.doc_id,
            page_number=img.page_number,
            image_path=img.image_path,
            image_type=img.image_type,
            width=img.width,
            height=img.height,
            description=img.description,
            created_at=str(img.created_at),
        )


@router.get("/images/{image_id}/file")
def serve_image_file(image_id: int):
    """이미지 파일 서빙."""
    with get_session() as session:
        img = session.query(DocImage).filter(DocImage.image_id == image_id).first()
        if not img:
            raise HTTPException(status_code=404, detail="Image not found")
        path = Path(img.image_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Image file not found on disk")
        media_type = f"image/{img.image_type or 'png'}"
        return FileResponse(path, media_type=media_type)
