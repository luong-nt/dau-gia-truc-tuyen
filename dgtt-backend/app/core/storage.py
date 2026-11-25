"""Lưu tệp upload trên ổ đĩa local (FR-05, FR-10).

Tệp KHÔNG được phục vụ dạng thư mục tĩnh vì có giấy tờ định danh. Muốn tải tệp
phải đi qua API có kiểm tra quyền, rồi dùng `resolve_path` để lấy đường dẫn thật.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.exceptions import BusinessRuleError

IMAGE_FORMATS = {"jpg", "jpeg", "png"}
DOCUMENT_FORMATS = {"pdf", "jpg", "jpeg", "png"}

_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class StoredFile:
    file_name: str  # tên gốc người dùng tải lên
    file_url: str  # đường dẫn tương đối trong STORAGE_DIR, lưu vào attachments.file_url
    file_format: str
    file_size: int


def _storage_root() -> Path:
    return Path(get_settings().storage_dir).resolve()


async def save_upload(file: UploadFile, subdir: str, allowed_formats: set[str] = DOCUMENT_FORMATS) -> StoredFile:
    original_name = file.filename or "file"
    file_format = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if file_format not in allowed_formats:
        raise BusinessRuleError(f"Định dạng tệp không được hỗ trợ. Chỉ chấp nhận: {', '.join(sorted(allowed_formats))}")

    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    target_dir = _storage_root() / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.{file_format}"
    target = target_dir / stored_name

    size = 0
    with target.open("wb") as out:
        while chunk := await file.read(_CHUNK_SIZE):
            size += len(chunk)
            if size > max_bytes:
                out.close()
                target.unlink(missing_ok=True)
                raise BusinessRuleError(f"Tệp vượt quá dung lượng cho phép ({get_settings().max_upload_mb} MB)")
            out.write(chunk)

    return StoredFile(
        file_name=original_name[:255],
        file_url=f"{subdir}/{stored_name}",
        file_format=file_format,
        file_size=size,
    )


def resolve_path(file_url: str) -> Path:
    """Đổi file_url (tương đối) thành đường dẫn thật, chặn truy cập ra ngoài STORAGE_DIR."""
    root = _storage_root()
    path = (root / file_url).resolve()
    if root not in path.parents:
        raise BusinessRuleError("Đường dẫn tệp không hợp lệ")
    return path
