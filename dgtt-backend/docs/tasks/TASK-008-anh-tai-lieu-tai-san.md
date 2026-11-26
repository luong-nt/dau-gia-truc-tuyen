# TASK-008: Upload, tải và xoá ảnh/tài liệu tài sản

- **Trạng thái:** REVIEW
- **FR/NFR liên quan:** FR-05 (ảnh JPG/PNG, hồ sơ liên quan), FR-07 (xem ảnh; hồ sơ nội bộ chỉ cho người có quyền), NFR-05, FR-26,
  AGENTS.md Mục 4.11
- **Module:** `app/modules/assets`
- **Phụ thuộc:** TASK-007, TASK-014 (chung các file của module `assets`)
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

Nhân viên tải lên ảnh (`ASSET_IMAGE`) và tài liệu (`ASSET_DOCUMENT`) cho tài sản, xoá tệp đã tải. Ảnh của tài sản đã công khai
được mọi người xem/tải; tài liệu là **hồ sơ nội bộ**, chỉ Nhân viên/Quản trị viên tải được. Chi tiết tài sản (TASK-007) liệt kê
tệp theo quyền.

## Phạm vi file được sửa (Codex)

- `app/modules/assets/router.py`
- `app/modules/assets/schemas.py`
- `app/modules/assets/service.py`
- `app/modules/assets/repository.py`
- `app/modules/assets/permissions.py`

Chỉ **dùng**: `app/core/storage.py` (`save_upload`, `resolve_path`, `IMAGE_FORMATS`, `DOCUMENT_FORMATS`).

## Đặc tả API

"Nội bộ" = STAFF, ADMIN. "Công khai" = Khách, BIDDER, AUCTIONEER (như TASK-007).

### `AttachmentOut`

`attachment_id`, `asset_id`, `file_type`, `file_name`, `file_format`, `file_size`, `display_order`, `uploaded_at`.
**Không** trả `file_url` (đường dẫn lưu trữ).

### 1. `POST /api/v1/assets/{asset_id}/attachments`

- **Vai trò:** STAFF (ADMIN, AUCTIONEER, BIDDER → 403).
- **Request multipart:** `file` (bắt buộc), `file_type` (bắt buộc).
- **Response 201:** `AttachmentOut`. `display_order` = lớn nhất hiện có của tài sản + 1 (bắt đầu từ 1).
- **Lỗi** (theo thứ tự):

| Tình huống | HTTP | `code` |
|---|---|---|
| Chưa đăng nhập | 401 | `UNAUTHORIZED` |
| Sai vai trò | 403 | `FORBIDDEN` |
| Thiếu `file` hoặc `file_type` | 422 | `VALIDATION_ERROR` |
| Tài sản không tồn tại | 404 | `NOT_FOUND` |
| `file_type` không phải `ASSET_IMAGE`/`ASSET_DOCUMENT` | 422 | `INVALID_FILE_TYPE` |
| `ASSET_IMAGE` không phải jpg/jpeg/png; `ASSET_DOCUMENT` không phải pdf/jpg/jpeg/png; vượt `MAX_UPLOAD_MB` | 422 | `BUSINESS_RULE_VIOLATION` (từ `save_upload`) |

- Lưu tệp bằng `save_upload(file, subdir=f"assets/{asset_id}", allowed_formats=...)`; lỗi thì không tạo dòng `attachments`.
- **Nhật ký:** `ADD_ASSET_ATTACHMENT`, `entity_type="asset"`, `entity_id=asset_id`, `new_value=file_name`.

### 2. `GET /api/v1/assets/{asset_id}/attachments/{attachment_id}`

- **Vai trò:** token tuỳ chọn (`OptionalUser`).
- **Được tải:** nội bộ: mọi tệp. Công khai: chỉ `ASSET_IMAGE` của tài sản `is_public = true`.
- **Response 200:** nội dung tệp (`resolve_path`), `Content-Type` theo định dạng: `image/jpeg` (jpg, jpeg), `image/png`,
  `application/pdf`.
- **Lỗi:** tài sản hoặc tệp không tồn tại, tệp không thuộc tài sản, hoặc người công khai không được tải (tài sản chưa công khai,
  hoặc tệp `ASSET_DOCUMENT`) → 404 `NOT_FOUND`. Token sai → 401.

### 3. `DELETE /api/v1/assets/{asset_id}/attachments/{attachment_id}`

- **Vai trò:** STAFF.
- **Response 204.** Xoá dòng `attachments` và tệp trên đĩa (tệp đã mất trên đĩa thì vẫn xoá dòng, không lỗi).
- **Lỗi:** 401; 403; 404 `NOT_FOUND` (tài sản/tệp không có, hoặc tệp không thuộc tài sản).
- **Nhật ký:** `DELETE_ASSET_ATTACHMENT`, `entity_type="asset"`, `entity_id=asset_id`, `old_value=file_name`.

### 4. Bổ sung `GET /api/v1/assets/{asset_id}` (TASK-007)

- Thêm trường `attachments: list[AttachmentOut]`, sắp `display_order` rồi `attachment_id` tăng dần.
  Nội bộ: mọi tệp. Công khai: chỉ `ASSET_IMAGE`.
- `DELETE /api/v1/assets/{asset_id}` (TASK-007) với tài sản có tệp: xoá cả dòng `attachments` (và tệp), trả 204.

## Quy tắc nghiệp vụ

1. Chỉ lưu tệp qua `save_upload`; chỉ đọc tệp qua `resolve_path`; không mở thư mục tĩnh (AGENTS.md Mục 4.11).
2. `log_activity` trước `commit`, `user_id` = nhân viên.
3. Không lộ `file_url` trong mọi response.

## Tiêu chí chấp nhận

- **AC-1:** Upload/xoá: không token → 401; ADMIN, AUCTIONEER, BIDDER → 403.
- **AC-2:** Upload ảnh PNG và tài liệu PDF → 201, đúng `file_type`, `file_name`, `file_format`, `file_size`, `display_order` 1, 2;
  không có `file_url`; DB có dòng (`asset_id`, `registration_id` null); tệp tồn tại trên đĩa với đúng nội dung; log `ADD_ASSET_ATTACHMENT`.
- **AC-3:** `file_type` khác (ví dụ `IDENTITY_DOCUMENT`) → 422 `INVALID_FILE_TYPE`; ảnh `.pdf`, tệp `.exe` → 422
  `BUSINESS_RULE_VIOLATION`; thiếu `file` → 422 `VALIDATION_ERROR`; tài sản không có → 404. Không tạo dòng.
- **AC-4:** Tải về: Khách tải được ảnh của tài sản công khai (đúng nội dung, `Content-Type`); Khách/BIDDER tải tài liệu, hoặc ảnh
  của tài sản chưa công khai → 404; STAFF/ADMIN tải được mọi tệp; tệp thuộc tài sản khác → 404.
- **AC-5:** Xoá → 204, dòng và tệp trên đĩa bị xoá, log `DELETE_ASSET_ATTACHMENT`; xoá lại → 404.
- **AC-6:** Chi tiết tài sản: công khai chỉ thấy ảnh, nội bộ thấy cả tài liệu, đúng thứ tự `display_order`; không có `file_url`.
- **AC-7:** Xoá tài sản có tệp (chưa có phiên) → 204, không còn dòng `attachments` của tài sản.

## Kế hoạch kiểm thử (Claude)

| AC | Test | File |
|---|---|---|
| AC-1 | `test_attachment_writes_auth` | `tests/api/test_asset_attachments_api.py` |
| AC-2 | `test_upload_attachments` | `tests/api/test_asset_attachments_api.py` |
| AC-3 | `test_upload_attachment_errors` | `tests/api/test_asset_attachments_api.py` |
| AC-4 | `test_download_attachment_permissions` | `tests/api/test_asset_attachments_api.py` |
| AC-5 | `test_delete_attachment` | `tests/api/test_asset_attachments_api.py` |
| AC-6 | `test_asset_detail_lists_attachments` | `tests/api/test_asset_attachments_api.py` |
| AC-7 | `test_delete_asset_with_attachments` | `tests/api/test_asset_attachments_api.py` |

## Ghi chú triển khai (Codex)

**KẾT LUẬN HIỆN TẠI CỦA CODEX: CHẤP THUẬN HOÀN TẤT, không còn chờ Codex.** Test chức năng/quyền tệp đạt,
lượt cuối full-system-10.xml không hồi quy. Claude cập nhật DONE theo phản hồi kiểm thử độc lập đã ghi bên dưới.

**Người triển khai: Claude** (theo chỉ thị người dùng 2026-11-26 trong `CLAUDE.md`; Codex kiểm thử độc lập).

- **File đã sửa:** `app/modules/assets/router.py`, `schemas.py` (`AttachmentOut`, `AssetDetailOut.attachments`),
  `service.py` (`add_attachment`, `get_attachment_file`, `delete_attachment`, lọc tệp trong chi tiết),
  `repository.py` (`get_attachment`, `next_display_order`), `permissions.py` (`can_view_attachment`).
- **Endpoint:** `POST /assets/{id}/attachments` (multipart `file`, `file_type`; STAFF), `GET /assets/{id}/attachments/{aid}`
  (`FileResponse`, token tuỳ chọn), `DELETE /assets/{id}/attachments/{aid}` (STAFF, 204).
- **Mã lỗi:** `INVALID_FILE_TYPE` (422), `BUSINESS_RULE_VIOLATION` (422, từ `save_upload`), `NOT_FOUND` (404),
  `VALIDATION_ERROR` (422, thiếu trường multipart).
- **Ghi chú:**
  - Lưu qua `save_upload(subdir="assets/{id}")`, đọc qua `resolve_path`; không mở thư mục tĩnh. `file_url` không có trong response.
  - Upload khoá dòng tài sản (`FOR UPDATE`) để `display_order` không trùng khi tải đồng thời; ghi DB lỗi thì xoá tệp vừa lưu.
  - Xoá tệp: xoá dòng, commit rồi mới xoá tệp trên đĩa (mất tệp thì bỏ qua).
  - Tải về và DELETE (204, trả `None`) giữ header `X-Access-Token` (NFR-04, theo phản hồi Codex ở TASK-006).
- **Khác đặc tả:** không.
- **Tự kiểm tra (2026-11-26 22:30):** ruff sạch. `tests/api/test_asset_attachments_api.py` 9/9, `test_assets_api.py` 12/12.
  `dgtt_test` toàn bộ: 342 passed, 2 skipped, 26 failed (official_result 8, reports 8, report_export 9 — task chưa làm;
  TC-RES-003 — thiếu Pango). Không hồi quy (333 → 342).

### Kiểm thử độc lập — Codex, 2026-11-26 21:05

- Đã chạy toàn bộ bộ test trên dgtt_test_codex: `logs/test-results/full-system-08.xml` có **342 passed, 26 failed,
  2 skipped**; không ca từng đạt bị hồi quy. **9/9 ca API tệp đính kèm tài sản đạt.**
- Review code: lưu qua save_upload, đọc qua resolve_path; DTO không lộ file_url; phân quyền ảnh công khai/tài liệu nội bộ;
  upload khoá dòng tài sản để cấp display_order, xoá dòng trước rồi xoá tệp sau commit, audit trước commit.
  FileResponse giữ token gia hạn cho người đã đăng nhập và vẫn cho khách tải ảnh công khai.
- Ruff check/format sạch. **TASK-008 đạt kiểm thử độc lập, đủ điều kiện hoàn tất.** Các ca đỏ còn lại thuộc
  TASK-009/010/011 chưa triển khai và PDF thật thiếu Pango; không phải hồi quy TASK-008.

## Kết quả kiểm thử (Claude)

_(Claude điền khi kiểm thử.)_

## Quyết định của người dùng

_(Không có.)_

## Lịch sử

- 2026-11-26 10:25 | Claude | TODO | Tạo task
- 2026-11-26 22:10 | Claude | IN_PROGRESS | Claude triển khai (mã TASK-007/014 đã có, đang REVIEW)
- 2026-11-26 22:30 | Claude | REVIEW | Bàn giao, chờ Codex kiểm thử độc lập
