# TASK-014: Quản lý người có tài sản

- **Trạng thái:** REVIEW
- **FR/NFR liên quan:** FR-05 (thông tin người có tài sản), NFR-05, FR-26
- **Module:** `app/modules/assets`
- **Phụ thuộc:** TASK-007 (chung các file của module `assets`)
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

Người có tài sản là bên liên quan, không có tài khoản (SRS). Nhân viên cần tìm, thêm và sửa thông tin người có tài sản để
gắn vào tài sản (TASK-007 dùng `owner_id`). Thông tin này là **nội bộ**: chỉ Nhân viên truy cập.

## Phạm vi file được sửa (Codex)

- `app/modules/assets/router.py`
- `app/modules/assets/schemas.py`
- `app/modules/assets/service.py`
- `app/modules/assets/repository.py`

## Đặc tả API

Mọi endpoint: **chỉ STAFF**. Không token → 401 `UNAUTHORIZED`; ADMIN, AUCTIONEER, BIDDER → 403 `FORBIDDEN`.

### `AssetOwnerOut`

`owner_id`, `owner_type`, `name`, `id_number`, `representative_name`, `phone`, `email`, `address`, `created_at`.

### Request `AssetOwnerRequest` (dùng cho POST và PUT; PUT gửi đủ các trường)

| Trường | Bắt buộc | Ràng buộc |
|---|---|---|
| `owner_type` | Có | `INDIVIDUAL` hoặc `ORGANIZATION` |
| `name` | Có | bỏ khoảng trắng hai đầu, 1–200 ký tự |
| `id_number` | Có | bỏ khoảng trắng hai đầu, 1–20 ký tự (CCCD hoặc mã số doanh nghiệp) |
| `representative_name` | Không | ≤ 100 ký tự |
| `phone` | Không | khớp `^[0-9+]{9,15}$` (như `users`) |
| `email` | Không | email hợp lệ, ≤ 100 ký tự |
| `address` | Không | ≤ 255 ký tự |

Sai ràng buộc → 422 `VALIDATION_ERROR`.

### 1. `GET /api/v1/asset-owners`

- **Query:** `keyword` (tuỳ chọn; không phân biệt hoa thường, khớp một phần `name`, `id_number` hoặc `representative_name`),
  `page`, `size`.
- **Response 200:** `Page[AssetOwnerOut]`, sắp `owner_id` giảm dần.

### 2. `GET /api/v1/asset-owners/{owner_id}`

- **Response 200:** `AssetOwnerOut`. Không tồn tại → 404 `NOT_FOUND`.

### 3. `POST /api/v1/asset-owners`

- **Response 201:** `AssetOwnerOut`.
- **Lỗi:** `id_number` đã tồn tại → 409 `OWNER_ID_NUMBER_EXISTS`.
- **Nhật ký:** `CREATE_ASSET_OWNER`, `entity_type="asset_owner"`, `entity_id`, `new_value = name`.

### 4. `PUT /api/v1/asset-owners/{owner_id}`

- **Response 200:** `AssetOwnerOut`.
- **Lỗi** (theo thứ tự): 401; 403; 422 `VALIDATION_ERROR`; 404 `NOT_FOUND`; `id_number` trùng với **người khác** → 409
  `OWNER_ID_NUMBER_EXISTS` (giữ nguyên `id_number` của chính mình là hợp lệ).
- **Nhật ký:** mỗi trường thật sự đổi một dòng `UPDATE_ASSET_OWNER` (`entity_type="asset_owner"`, `field_name`, `old_value`,
  `new_value`). Không đổi gì → 200, không log.

## Quy tắc nghiệp vụ

1. `id_number` duy nhất (`uq_asset_owners_id_number`). Kiểm tra trước khi ghi để trả 409 thay vì lỗi 500.
2. Không xoá người có tài sản (không có endpoint DELETE).
3. `log_activity` trước `commit`, `user_id` = nhân viên.

## Tiêu chí chấp nhận

- **AC-1:** Cả 4 endpoint: không token → 401; ADMIN, AUCTIONEER, BIDDER → 403.
- **AC-2:** POST hợp lệ → 201, dữ liệu đã bỏ khoảng trắng; DB có dòng; log `CREATE_ASSET_OWNER`.
- **AC-3:** POST `id_number` trùng → 409 `OWNER_ID_NUMBER_EXISTS`; `owner_type` sai, `name` rỗng, `id_number` > 20 ký tự,
  `phone` sai mẫu, `email` sai → 422 `VALIDATION_ERROR`. Không tạo dòng.
- **AC-4:** PUT đổi trường → 200, DB đổi, mỗi trường một log `UPDATE_ASSET_OWNER` đúng old/new; giữ nguyên `id_number` của mình hợp lệ;
  trùng `id_number` người khác → 409; không tồn tại → 404; không đổi gì → không log.
- **AC-5:** GET danh sách tìm theo tên/số giấy tờ/người đại diện không phân biệt hoa thường, phân trang; GET chi tiết đúng, 404 khi không có.

## Kế hoạch kiểm thử (Claude)

| AC | Test | File |
|---|---|---|
| AC-1 | `test_owners_without_token_401`, `test_owners_require_staff` | `tests/api/test_asset_owners_api.py` |
| AC-2 | `test_create_owner` | `tests/api/test_asset_owners_api.py` |
| AC-3 | `test_create_owner_errors` | `tests/api/test_asset_owners_api.py` |
| AC-4 | `test_update_owner` | `tests/api/test_asset_owners_api.py` |
| AC-5 | `test_search_and_get_owner` | `tests/api/test_asset_owners_api.py` |

## Ghi chú triển khai (Codex)

**KẾT LUẬN HIỆN TẠI CỦA CODEX: CHẤP THUẬN HOÀN TẤT, không còn chờ Codex.** 6/6 ca API người có tài sản và test
tạo đồng thời trùng giấy tờ đạt, lượt cuối full-system-10.xml không hồi quy. Claude cập nhật DONE.

**Người triển khai: Claude** (theo chỉ thị người dùng 2026-11-26 trong `CLAUDE.md`; Codex kiểm thử độc lập).

- **File đã sửa:** `app/modules/assets/router.py`, `schemas.py` (`AssetOwnerRequest`, `AssetOwnerOut` thêm `created_at`),
  `service.py`, `repository.py`.
- **Endpoint:** `GET /asset-owners`, `GET /asset-owners/{id}`, `POST /asset-owners`, `PUT /asset-owners/{id}`; chỉ STAFF.
- **Mã lỗi:** `OWNER_ID_NUMBER_EXISTS` (409), `NOT_FOUND` (404), `VALIDATION_ERROR` (422; `phone` theo mẫu
  `^[0-9+]{9,15}$`, `email` là `EmailStr` như module `users`).
- **Tranh chấp:** kiểm tra trùng trước khi ghi, và nếu hai yêu cầu đồng thời cùng vượt qua thì bắt `IntegrityError` của đúng
  ràng buộc `uq_asset_owners_id_number` → 409 (cả POST và PUT). Test: `test_concurrent_create_same_owner_id_number`.
  PUT khoá dòng người có tài sản (`FOR UPDATE`).
- **Sửa test của Claude:** `tests/factories.py::create_owner` mặc định email `@dgtt.local` bị `EmailStr` từ chối (tên miền
  dành riêng) → đổi thành `chu.tai.san@taisan.vn`. Lỗi ở dữ liệu test, không phải mã ứng dụng.
- **Khác đặc tả:** không.
- **Tự kiểm tra (2026-11-26 22:05):** ruff sạch. `tests/api/test_asset_owners_api.py` 6/6, test đồng thời 2/2.
  `dgtt_test` toàn bộ: 333 passed, 2 skipped, 35 failed (chỉ thuộc TASK-008/009/010/011 chưa làm và TC-RES-003 thiếu Pango).

### Kiểm thử độc lập — Codex, 2026-11-26 21:01

- Đã chạy toàn bộ bộ test trên dgtt_test_codex: `logs/test-results/full-system-08.xml` có **342 passed, 26 failed,
  2 skipped**; không ca từng đạt bị hồi quy. 6 ca API người có tài sản và ca tạo đồng thời trùng id_number đều đạt.
- Đã kiểm tra quyền chỉ STAFF, dữ liệu nội bộ, kiểm tra ràng buộc trùng và log trước commit qua test và review code.
  Ruff check/format sạch. **TASK-014 đạt kiểm thử độc lập, đủ điều kiện hoàn tất.** Các ca đỏ còn lại thuộc task
  chưa triển khai và PDF thật thiếu Pango, không phải lỗi TASK-014.

## Kết quả kiểm thử (Claude)

_(Claude điền khi kiểm thử.)_

## Quyết định của người dùng

_(Không có.)_

## Lịch sử

- 2026-11-26 10:10 | Claude | TODO | Tạo task (tách từ backlog TASK-007 để mỗi task 3–6 endpoint)
- 2026-11-26 21:50 | Claude | IN_PROGRESS | Claude triển khai (mã TASK-007 đã có, đang REVIEW)
- 2026-11-26 22:05 | Claude | REVIEW | Bàn giao, chờ Codex kiểm thử độc lập
