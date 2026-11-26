"""TASK-008: upload, tải, xoá ảnh/tài liệu tài sản."""

import pytest
from sqlalchemy import select

from app.core.storage import resolve_path
from app.db.models import ActivityLog, Attachment
from app.db.session import SessionLocal
from seeds.seed_dev import seed
from tests.factories import create_asset, login_headers

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"anh-tai-san-test" * 10
PDF_BYTES = b"%PDF-1.4\n% tai lieu tai san test\n"
JPG_BYTES = b"\xff\xd8\xff\xe0" + b"jpg-test" * 10
ATTACHMENT_FIELDS = {
    "attachment_id",
    "asset_id",
    "file_type",
    "file_name",
    "file_format",
    "file_size",
    "display_order",
    "uploaded_at",
}


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code, response.text


def _url(asset_id: int, attachment_id: int | None = None) -> str:
    base = f"/api/v1/assets/{asset_id}/attachments"
    return base if attachment_id is None else f"{base}/{attachment_id}"


async def _upload(client, headers, asset_id: int, file_type: str, name: str, content: bytes, mime: str):
    return await client.post(
        _url(asset_id), data={"file_type": file_type}, files={"file": (name, content, mime)}, headers=headers
    )


async def _rows(asset_id: int) -> list[Attachment]:
    async with SessionLocal() as s:
        rows = await s.scalars(
            select(Attachment).where(Attachment.asset_id == asset_id).order_by(Attachment.attachment_id)
        )
        return list(rows)


async def _logs(asset_id: int, action: str) -> list[ActivityLog]:
    async with SessionLocal() as s:
        rows = await s.scalars(
            select(ActivityLog)
            .where(ActivityLog.entity_type == "asset", ActivityLog.entity_id == asset_id, ActivityLog.action == action)
            .order_by(ActivityLog.log_id)
        )
        return list(rows)


async def _setup(db, prefix: str, *, is_public: bool = True):
    data = await seed(db, prefix=prefix, bidder_count=1)
    asset = await create_asset(db, created_by=data.users["staff"].user_id, is_public=is_public)
    return data.users, asset


async def _with_files(client, db, prefix: str, *, is_public: bool = True):
    """Tài sản có 1 ảnh PNG (display_order 1) và 1 tài liệu PDF (display_order 2)."""
    users, asset = await _setup(db, prefix, is_public=is_public)
    h = await login_headers(client, users["staff"].username)
    image = await _upload(client, h, asset.asset_id, "ASSET_IMAGE", "mat-tien.png", PNG_BYTES, "image/png")
    assert image.status_code == 201, image.text
    doc = await _upload(
        client, h, asset.asset_id, "ASSET_DOCUMENT", "giay-chung-nhan.pdf", PDF_BYTES, "application/pdf"
    )
    assert doc.status_code == 201, doc.text
    return users, asset, h, image.json(), doc.json()


async def test_attachment_upload_without_token_401(client):
    """TASK-008 AC-1: upload/xoá không token -> 401"""
    response = await client.post(
        _url(1), data={"file_type": "ASSET_IMAGE"}, files={"file": ("a.png", PNG_BYTES, "image/png")}
    )
    _assert_error(response, 401, "UNAUTHORIZED")
    _assert_error(await client.delete(_url(1, 1)), 401, "UNAUTHORIZED")


@pytest.mark.db
async def test_attachment_writes_auth(client, db, prefix):
    """TASK-008 AC-1: ADMIN, AUCTIONEER, BIDDER upload/xoá -> 403 FORBIDDEN"""
    users, asset, _, image, _ = await _with_files(client, db, prefix)
    for role in ("admin", "auctioneer", "bidder1"):
        h = await login_headers(client, users[role].username)
        response = await _upload(client, h, asset.asset_id, "ASSET_IMAGE", "x.png", PNG_BYTES, "image/png")
        _assert_error(response, 403, "FORBIDDEN")
        _assert_error(await client.delete(_url(asset.asset_id, image["attachment_id"]), headers=h), 403, "FORBIDDEN")
    assert len(await _rows(asset.asset_id)) == 2


@pytest.mark.db
async def test_upload_attachments(client, db, prefix):
    """TASK-008 AC-2: upload PNG + PDF -> 201, display_order 1, 2, không file_url, DB + tệp trên đĩa, log"""
    users, asset, _, image, doc = await _with_files(client, db, prefix)

    for out in (image, doc):
        assert set(out) >= ATTACHMENT_FIELDS
        assert "file_url" not in out
        assert out["asset_id"] == asset.asset_id
    assert (
        image["file_type"],
        image["file_name"],
        image["file_format"],
        image["file_size"],
        image["display_order"],
    ) == (
        "ASSET_IMAGE",
        "mat-tien.png",
        "png",
        len(PNG_BYTES),
        1,
    )
    assert (doc["file_type"], doc["file_name"], doc["file_format"], doc["file_size"], doc["display_order"]) == (
        "ASSET_DOCUMENT",
        "giay-chung-nhan.pdf",
        "pdf",
        len(PDF_BYTES),
        2,
    )

    rows = await _rows(asset.asset_id)
    assert [r.attachment_id for r in rows] == [image["attachment_id"], doc["attachment_id"]]
    for row, content in zip(rows, (PNG_BYTES, PDF_BYTES), strict=True):
        assert row.registration_id is None
        path = resolve_path(row.file_url)
        assert path.read_bytes() == content
    logs = await _logs(asset.asset_id, "ADD_ASSET_ATTACHMENT")
    assert [(log.user_id, log.new_value) for log in logs] == [
        (users["staff"].user_id, "mat-tien.png"),
        (users["staff"].user_id, "giay-chung-nhan.pdf"),
    ]

    # ASSET_DOCUMENT chấp nhận cả ảnh jpg
    h = await login_headers(client, users["staff"].username)
    response = await _upload(client, h, asset.asset_id, "ASSET_DOCUMENT", "ban-ve.jpg", JPG_BYTES, "image/jpeg")
    assert response.status_code == 201, response.text
    assert response.json()["display_order"] == 3


@pytest.mark.db
async def test_upload_attachment_errors(client, db, prefix):
    """TASK-008 AC-3: file_type sai 422 INVALID_FILE_TYPE; định dạng sai 422 BUSINESS_RULE_VIOLATION;
    thiếu file 422 VALIDATION_ERROR; tài sản không có 404; không tạo dòng"""
    users, asset = await _setup(db, prefix)
    h = await login_headers(client, users["staff"].username)
    aid = asset.asset_id

    for file_type in ("IDENTITY_DOCUMENT", "DEPOSIT_RECEIPT", "OTHER", "ANH"):
        response = await _upload(client, h, aid, file_type, "a.png", PNG_BYTES, "image/png")
        _assert_error(response, 422, "INVALID_FILE_TYPE")
    _assert_error(
        await _upload(client, h, aid, "ASSET_IMAGE", "anh.pdf", PDF_BYTES, "application/pdf"),
        422,
        "BUSINESS_RULE_VIOLATION",
    )
    _assert_error(
        await _upload(client, h, aid, "ASSET_DOCUMENT", "virus.exe", b"MZ", "application/octet-stream"),
        422,
        "BUSINESS_RULE_VIOLATION",
    )
    _assert_error(await client.post(_url(aid), data={"file_type": "ASSET_IMAGE"}, headers=h), 422, "VALIDATION_ERROR")
    _assert_error(
        await client.post(_url(aid), files={"file": ("a.png", PNG_BYTES, "image/png")}, headers=h),
        422,
        "VALIDATION_ERROR",
    )
    _assert_error(await _upload(client, h, 999_999, "ASSET_IMAGE", "a.png", PNG_BYTES, "image/png"), 404, "NOT_FOUND")
    assert await _rows(aid) == []
    assert await _logs(aid, "ADD_ASSET_ATTACHMENT") == []


@pytest.mark.db
async def test_upload_attachment_too_large(client, db, prefix, monkeypatch):
    """TASK-008 AC-3: tệp vượt MAX_UPLOAD_MB -> 422 BUSINESS_RULE_VIOLATION, không tạo dòng"""
    from app.core.config import get_settings

    users, asset = await _setup(db, prefix)
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    h = await login_headers(client, users["staff"].username)
    big = b"\x89PNG" + b"0" * (1024 * 1024 + 10)
    _assert_error(
        await _upload(client, h, asset.asset_id, "ASSET_IMAGE", "to.png", big, "image/png"),
        422,
        "BUSINESS_RULE_VIOLATION",
    )
    assert await _rows(asset.asset_id) == []


@pytest.mark.db
async def test_download_attachment_permissions(client, db, prefix):
    """TASK-008 AC-4: Khách tải ảnh tài sản công khai; tài liệu / tài sản chưa công khai -> 404 với công khai;
    nội bộ tải mọi tệp; tệp của tài sản khác -> 404"""
    users, asset, h_staff, image, doc = await _with_files(client, db, prefix)
    _, hidden, _, hidden_image, _ = await _with_files(client, db, prefix + "h", is_public=False)
    h_bidder = await login_headers(client, users["bidder1"].username)
    h_auctioneer = await login_headers(client, users["auctioneer"].username)
    h_admin = await login_headers(client, users["admin"].username)

    for headers in (None, h_bidder, h_auctioneer, h_staff, h_admin):
        response = await client.get(_url(asset.asset_id, image["attachment_id"]), headers=headers)
        assert response.status_code == 200, response.text
        assert response.content == PNG_BYTES
        assert response.headers["content-type"].startswith("image/png")

    for headers in (None, h_bidder, h_auctioneer):
        _assert_error(await client.get(_url(asset.asset_id, doc["attachment_id"]), headers=headers), 404, "NOT_FOUND")
        response = await client.get(_url(hidden.asset_id, hidden_image["attachment_id"]), headers=headers)
        _assert_error(response, 404, "NOT_FOUND")

    for headers in (h_staff, h_admin):
        response = await client.get(_url(asset.asset_id, doc["attachment_id"]), headers=headers)
        assert response.status_code == 200, response.text
        assert response.content == PDF_BYTES
        assert response.headers["content-type"].startswith("application/pdf")
        response = await client.get(_url(hidden.asset_id, hidden_image["attachment_id"]), headers=headers)
        assert response.status_code == 200, response.text

    # tệp thuộc tài sản khác, tệp/tài sản không tồn tại
    _assert_error(
        await client.get(_url(asset.asset_id, hidden_image["attachment_id"]), headers=h_staff), 404, "NOT_FOUND"
    )
    _assert_error(await client.get(_url(asset.asset_id, 999_999), headers=h_staff), 404, "NOT_FOUND")
    _assert_error(await client.get(_url(999_999, image["attachment_id"]), headers=h_staff), 404, "NOT_FOUND")


@pytest.mark.db
async def test_delete_attachment(client, db, prefix):
    """TASK-008 AC-5: xoá -> 204, mất dòng + tệp, log DELETE_ASSET_ATTACHMENT; xoá lại -> 404"""
    users, asset, h, image, doc = await _with_files(client, db, prefix)
    rows = {r.attachment_id: r for r in await _rows(asset.asset_id)}
    path = resolve_path(rows[image["attachment_id"]].file_url)
    assert path.exists()

    response = await client.delete(_url(asset.asset_id, image["attachment_id"]), headers=h)
    assert response.status_code == 204, response.text
    assert [r.attachment_id for r in await _rows(asset.asset_id)] == [doc["attachment_id"]]
    assert not path.exists()
    logs = await _logs(asset.asset_id, "DELETE_ASSET_ATTACHMENT")
    assert [(log.user_id, log.old_value) for log in logs] == [(users["staff"].user_id, "mat-tien.png")]

    _assert_error(await client.delete(_url(asset.asset_id, image["attachment_id"]), headers=h), 404, "NOT_FOUND")
    other = await create_asset(db, created_by=users["staff"].user_id)
    _assert_error(await client.delete(_url(other.asset_id, doc["attachment_id"]), headers=h), 404, "NOT_FOUND")
    assert len(await _rows(asset.asset_id)) == 1


@pytest.mark.db
async def test_asset_detail_lists_attachments(client, db, prefix):
    """TASK-008 AC-6: chi tiết tài sản: công khai chỉ thấy ảnh; nội bộ thấy cả tài liệu, đúng thứ tự; không file_url"""
    users, asset, h_staff, image, doc = await _with_files(client, db, prefix)
    second = await _upload(client, h_staff, asset.asset_id, "ASSET_IMAGE", "ben-hong.jpg", JPG_BYTES, "image/jpeg")
    assert second.status_code == 201, second.text

    response = await client.get(f"/api/v1/assets/{asset.asset_id}")
    assert response.status_code == 200, response.text
    files = response.json()["attachments"]
    assert [f["attachment_id"] for f in files] == [image["attachment_id"], second.json()["attachment_id"]]
    assert all("file_url" not in f and f["file_type"] == "ASSET_IMAGE" for f in files)
    assert "file_url" not in response.text

    response = await client.get(f"/api/v1/assets/{asset.asset_id}", headers=h_staff)
    assert response.status_code == 200, response.text
    files = response.json()["attachments"]
    assert [f["attachment_id"] for f in files] == [
        image["attachment_id"],
        doc["attachment_id"],
        second.json()["attachment_id"],
    ]
    assert [f["display_order"] for f in files] == [1, 2, 3]
    assert "file_url" not in response.text


@pytest.mark.db
async def test_delete_asset_with_attachments(client, db, prefix):
    """TASK-008 AC-7: xoá tài sản có tệp (chưa có phiên) -> 204, không còn dòng attachments"""
    _, asset, h, _, _ = await _with_files(client, db, prefix)
    response = await client.delete(f"/api/v1/assets/{asset.asset_id}", headers=h)
    assert response.status_code == 204, response.text
    assert await _rows(asset.asset_id) == []
