import io
import logging
import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_UPLOAD_ROOT = _PROJECT_ROOT / "static" / "uploads"
PUBLIC_ROOT = "/static/uploads"
ALLOWED_KINDS = {"categories", "products", "hero", "about"}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 5 * 1024 * 1024
WEBP_QUALITY = 82
OUTPUT_EXT = ".webp"

logger = logging.getLogger("uvicorn.error")


def _paths(kind: str) -> tuple[Path, str]:
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"Unknown upload kind: {kind}")
    return _UPLOAD_ROOT / kind, f"{PUBLIC_ROOT}/{kind}"


def _ensure_dir(kind: str) -> Path:
    upload_dir, _ = _paths(kind)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _is_webp(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def _has_alpha(image: Image.Image) -> bool:
    if image.mode in {"RGBA", "LA", "PA"}:
        return True
    if image.mode == "P" and "transparency" in image.info:
        return True
    return False


def _to_webp(data: bytes) -> bytes:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image file is invalid.",
        ) from exc
    image = ImageOps.exif_transpose(image) or image
    converted = image.convert("RGBA") if _has_alpha(image) else image.convert("RGB")
    buffer = io.BytesIO()
    converted.save(
        buffer,
        format="WEBP",
        quality=WEBP_QUALITY,
        method=4,
    )
    return buffer.getvalue()


def _write(dest: Path, data: bytes) -> None:
    try:
        dest.write_bytes(data)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the image file.",
        ) from exc


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
    original_size = len(data)
    if original_size > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image must be 5MB or smaller.",
        )

    if _is_webp(data):
        payload = data
        logger.info(
            "upload %s webp passthrough original=%d bytes",
            kind,
            original_size,
        )
    else:
        payload = _to_webp(data)
        logger.info(
            "upload %s converted %s %d -> webp %d bytes",
            kind,
            ext.lstrip("."),
            original_size,
            len(payload),
        )

    upload_dir = _ensure_dir(kind)
    _, public_prefix = _paths(kind)
    filename = f"{uuid.uuid4().hex}{OUTPUT_EXT}"
    _write(upload_dir / filename, payload)
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
