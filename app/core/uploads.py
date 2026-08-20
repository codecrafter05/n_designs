import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_UPLOAD_ROOT = _PROJECT_ROOT / "static" / "uploads"
PUBLIC_ROOT = "/static/uploads"
ALLOWED_KINDS = {"categories", "products", "hero", "about"}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 5 * 1024 * 1024


def _paths(kind: str) -> tuple[Path, str]:
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"Unknown upload kind: {kind}")
    return _UPLOAD_ROOT / kind, f"{PUBLIC_ROOT}/{kind}"


def _ensure_dir(kind: str) -> Path:
    upload_dir, _ = _paths(kind)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def save_image(upload: UploadFile, kind: str = "categories") -> str:
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

    upload_dir = _ensure_dir(kind)
    _, public_prefix = _paths(kind)
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = upload_dir / filename
    dest.write_bytes(data)
    return f"{public_prefix}/{filename}"


def delete_image(public_path: str | None, kind: str | None = None) -> None:
    if not public_path:
        return
    kinds = (kind,) if kind else tuple(ALLOWED_KINDS)
    for item in kinds:
        upload_dir, public_prefix = _paths(item)
        if not public_path.startswith(public_prefix + "/"):
            continue
        filename = Path(public_path).name
        if filename != Path(public_path).name or ".." in filename:
            return
        path = (upload_dir / filename).resolve()
        try:
            path.relative_to(upload_dir.resolve())
        except ValueError:
            return
        if path.is_file():
            os.remove(path)
        return


def save_category_image(upload: UploadFile) -> str:
    return save_image(upload, "categories")


def delete_category_image(public_path: str | None) -> None:
    delete_image(public_path, "categories")
