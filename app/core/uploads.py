import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = _PROJECT_ROOT / "static" / "uploads" / "categories"
PUBLIC_PREFIX = "/static/uploads/categories"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 5 * 1024 * 1024


def _ensure_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def save_category_image(upload: UploadFile) -> str:
    ext = Path(upload.filename or "").suffix.lower()
    if ext == ".jpeg":
        ext = ".jpg"
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image must be JPG, PNG, or WebP.",
        )
    content_type = (upload.content_type or "").lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image must be JPG, PNG, or WebP.",
        )

    data = upload.file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty image file.")
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image must be 5MB or smaller.",
        )

    _ensure_dir()
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / filename
    dest.write_bytes(data)
    return f"{PUBLIC_PREFIX}/{filename}"


def delete_category_image(public_path: str | None) -> None:
    if not public_path or not public_path.startswith(PUBLIC_PREFIX + "/"):
        return
    filename = Path(public_path).name
    if filename != Path(public_path).name or ".." in filename:
        return
    path = (UPLOAD_DIR / filename).resolve()
    try:
        path.relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        return
    if path.is_file():
        os.remove(path)
