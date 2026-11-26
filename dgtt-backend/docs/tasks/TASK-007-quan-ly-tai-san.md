# TASK-007: Thêm, sửa, xoá, ngừng và tra cứu tài sản

- **Trạng thái:** REVIEW
- **FR/NFR liên quan:** FR-05, FR-06, FR-07, NFR-05, FR-26, AGENTS.md Mục 5.7
- **Module:** `app/modules/assets`
- **Phụ thuộc:** TASK-013 (kiểu `Money` cho `starting_price` trong chi tiết tài sản)
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

Nhân viên quản lý tài sản đấu giá: thêm, sửa (có lý do khi tài sản đã công khai), xoá tài sản chưa có lịch sử, chuyển sang
ngừng (`SUSPENDED_CANCELLED`). Mọi người (kể cả Khách) tra cứu và xem chi tiết tài sản **đã công khai**; Nhân viên/Quản trị viên
thấy cả tài sản chưa công khai và thông tin người có tài sản.

Ngoài phạm vi: người có tài sản (TASK-014), ảnh/tài liệu (TASK-008). Người có tài sản trong test được tạo bằng `tests/factories.py`.

## Phạm vi file được sửa (Codex)

- `app/modules/assets/router.py`
- `app/modules/assets/schemas.py`
- `app/modules/assets/service.py`
- `app/modules/assets/repository.py`
- `app/modules/assets/permissions.py` (tạo mới nếu cần)

Chỉ **dùng**: `app/modules/sessions/repository.py` (`has_active_session`, `get_asset_for_update`), `app/core/money.py`,
`app/core/pagination.py`. Router `assets` đã được gắn vào `app/main.py`.

## Đặc tả API

Quy ước chung:
- "Nội bộ" = STAFF hoặc ADMIN. "Công khai" = Khách (không token), BIDDER, AUCTIONEER.
- Endpoint ghi (POST/PUT/DELETE/PATCH) chỉ cho **STAFF**; ADMIN, AUCTIONEER, BIDDER → 403 `FORBIDDEN`.
- Tài sản `is_public = false` với người công khai coi như **không tồn tại** → 404 `NOT_FOUND`.

### `AssetOut`

| Trường | Ghi chú |
|---|---|
| `asset_id`, `asset_code`, `name`, `description`, `status`, `is_public`, `created_at` | |

### `AssetDetailOut` = `AssetOut` + 

| Trường | Ghi chú |
|---|---|
| `owner` | Nội bộ: `{owner_id, owner_type, name, id_number, representative_name, phone, email, address}`. Công khai: `null` |
| `sessions` | Các phiên của tài sản, sắp `start_time` giảm dần: `{session_id, code ("PDG-{id}"), status, starting_price (Money), start_time, end_time}`. Công khai: **bỏ** phiên `DRAFT` |

### 1. `GET /api/v1/assets`

- **Vai trò:** mọi người (token tuỳ chọn; token có gửi thì phải hợp lệ, dùng `OptionalUser`).
- **Query:** `keyword` (tuỳ chọn; tìm không phân biệt hoa thường trong `name` **hoặc** `asset_code`), `status` (một giá trị
  `AssetStatus`), `min_price`, `max_price` (số nguyên ≥ 0), `page`, `size` (`Pagination`).
- Lọc giá: tài sản có **ít nhất một phiên** mà người gọi được thấy (quy tắc `sessions` ở trên) với
  `min_price ≤ starting_price ≤ max_price` (thiếu cận nào thì bỏ cận đó).
- **Response 200:** `Page[AssetOut]`, sắp `created_at` giảm dần rồi `asset_id` giảm dần. Công khai chỉ có `is_public = true`.
- **Lỗi:** `status` sai giá trị, giá âm → 422 `VALIDATION_ERROR`; `min_price > max_price` → 422 `INVALID_PRICE_RANGE`;
  token sai → 401.

### 2. `GET /api/v1/assets/{asset_id}`

- **Vai trò:** như mục 1.
- **Response 200:** `AssetDetailOut`.
- **Lỗi:** không tồn tại, hoặc chưa công khai với người công khai → 404 `NOT_FOUND`.

### 3. `POST /api/v1/assets`

- **Vai trò:** STAFF.
- **Request JSON:**

| Trường | Bắt buộc | Ràng buộc |
|---|---|---|
| `asset_code` | Có | bỏ khoảng trắng hai đầu, 1–30 ký tự |
| `owner_id` | Có | int |
| `name` | Có | bỏ khoảng trắng, 1–200 ký tự |
| `description` | Không | ≤ 5000 ký tự |
| `is_public` | Không | bool, mặc định `false` |

- **Response 201:** `AssetDetailOut` (góc nhìn nội bộ). `status = UPCOMING`, `created_by` = nhân viên.
- **Lỗi:** 401; 403; 422 `VALIDATION_ERROR`; `owner_id` không tồn tại → 422 `OWNER_NOT_FOUND`;
  `asset_code` trùng → 409 `ASSET_CODE_EXISTS`.
- **Nhật ký:** `CREATE_ASSET`, `entity_type="asset"`, `entity_id`, `new_value = asset_code`.

### 4. `PUT /api/v1/assets/{asset_id}`

- **Vai trò:** STAFF.
- **Request JSON:** `name` (bắt buộc), `description`, `owner_id` (bắt buộc), `is_public` (bắt buộc), `reason` (tuỳ chọn,
  bỏ khoảng trắng, ≤ 500). **Không** cho đổi `asset_code` và `status` (gửi kèm thì bỏ qua).
- **Response 200:** `AssetDetailOut` (nội bộ).
- **Lỗi** (theo thứ tự): 401; 403; 422 `VALIDATION_ERROR`; 404 `NOT_FOUND`; `owner_id` không tồn tại → 422 `OWNER_NOT_FOUND`;
  tài sản **đang công khai** (giá trị `is_public` **trước** khi sửa là `true`) mà có trường thay đổi và `reason` rỗng/thiếu
  → 422 `REASON_REQUIRED`.
- **Nhật ký:** **mỗi trường thật sự thay đổi** một dòng `UPDATE_ASSET` (`entity_type="asset"`, `field_name` ∈
  `name`, `description`, `owner_id`, `is_public`; `old_value`, `new_value` dạng chuỗi; `reason`). Không đổi gì → 200, không log.

### 5. `DELETE /api/v1/assets/{asset_id}`

- **Vai trò:** STAFF.
- **Response 204.** Xoá tài sản (và các dòng `attachments` của tài sản nếu có).
- **Lỗi:** 401; 403; 404 `NOT_FOUND`; tài sản đã gắn **bất kỳ** phiên nào (mọi trạng thái) → 409 `ASSET_HAS_SESSIONS`.
- **Nhật ký:** `DELETE_ASSET`, `entity_id = asset_id`, `old_value = asset_code`.

### 6. `PATCH /api/v1/assets/{asset_id}/status`

- **Vai trò:** STAFF.
- **Request JSON:** `status` (chỉ chấp nhận `SUSPENDED_CANCELLED`), `reason` (bắt buộc, bỏ khoảng trắng, 1–500).
- **Response 200:** `AssetDetailOut` (nội bộ).
- **Lỗi** (theo thứ tự): 401; 403; 422 `VALIDATION_ERROR` (thiếu/rỗng `reason`); 404 `NOT_FOUND`;
  `status` khác `SUSPENDED_CANCELLED`, hoặc tài sản không ở `UPCOMING` → 422 `INVALID_ASSET_STATUS_TRANSITION`;
  tài sản có phiên chưa kết thúc (`sessions.repository.has_active_session`) → 409 `ASSET_HAS_ACTIVE_SESSION`.
- **Nhật ký:** `UPDATE_ASSET_STATUS`, `field_name="status"`, `old_value="UPCOMING"`, `new_value="SUSPENDED_CANCELLED"`, `reason`.

## Quy tắc nghiệp vụ

1. Tài sản mới luôn `UPCOMING` (AGENTS.md Mục 5.7). `status` chỉ đổi qua endpoint 6 (và các module sessions/results).
2. Giá khởi điểm/bước giá thuộc phiên, không thuộc tài sản (FR-05).
3. `log_activity` trước `commit`, `user_id` = nhân viên. Dùng `utcnow()` nếu cần thời gian.
4. Không trả `id_number`, `phone`, `email`, `address` của người có tài sản cho người công khai.

## Tiêu chí chấp nhận

- **AC-1:** Endpoint ghi: không token → 401; ADMIN, AUCTIONEER, BIDDER → 403.
- **AC-2:** POST hợp lệ → 201, `status = UPCOMING`, `is_public` đúng, `owner` đầy đủ; DB có dòng đúng `created_by`; log `CREATE_ASSET`.
- **AC-3:** POST `asset_code` trùng → 409 `ASSET_CODE_EXISTS`; `owner_id` không có → 422 `OWNER_NOT_FOUND`;
  thiếu/rỗng `name`, `asset_code` dài > 30 → 422 `VALIDATION_ERROR`. Không tạo dòng.
- **AC-4:** PUT tài sản chưa công khai không cần `reason`; mỗi trường đổi một log `UPDATE_ASSET` đúng `field_name/old/new`;
  `asset_code`, `status` gửi kèm không bị đổi.
- **AC-5:** PUT tài sản đang công khai có thay đổi mà thiếu `reason` → 422 `REASON_REQUIRED`, không đổi DB; có `reason` → 200,
  log có `reason`. PUT không đổi gì → 200, không log.
- **AC-6:** DELETE tài sản chưa có phiên → 204, dòng bị xoá, log `DELETE_ASSET`; có phiên → 409 `ASSET_HAS_SESSIONS`; không có → 404.
- **AC-7:** PATCH status `UPCOMING` → `SUSPENDED_CANCELLED` có lý do → 200, log `UPDATE_ASSET_STATUS`; thiếu lý do → 422
  `VALIDATION_ERROR`; tài sản `IN_AUCTION`/`ENDED`/`SUSPENDED_CANCELLED` hoặc `status` khác → 422
  `INVALID_ASSET_STATUS_TRANSITION`; có phiên đang mở nhận hồ sơ → 409 `ASSET_HAS_ACTIVE_SESSION`.
- **AC-8:** GET danh sách: Khách/BIDDER/AUCTIONEER chỉ thấy tài sản công khai; STAFF/ADMIN thấy cả chưa công khai;
  `keyword` tìm theo tên và mã, không phân biệt hoa thường; lọc `status`; phân trang có `total`.
- **AC-9:** Lọc giá theo phiên: `min_price/max_price` chọn đúng tài sản có phiên trong khoảng; `min_price > max_price` → 422
  `INVALID_PRICE_RANGE`; giá âm hoặc `status` sai → 422 `VALIDATION_ERROR`; Khách không lọc được theo phiên `DRAFT`.
- **AC-10:** GET chi tiết: công khai thấy tài sản công khai, `owner = null`, không có phiên `DRAFT`, `starting_price` dạng
  chuỗi chữ số; tài sản chưa công khai → 404; nội bộ thấy `owner` và mọi phiên; không tồn tại → 404.

## Kế hoạch kiểm thử (Claude)

| AC | Test | File |
|---|---|---|
| AC-1 | `test_asset_writes_require_staff` | `tests/api/test_assets_api.py` |
| AC-2, AC-3 | `test_create_asset`, `test_create_asset_errors` | `tests/api/test_assets_api.py` |
| AC-4, AC-5 | `test_update_asset_not_public`, `test_update_public_asset_requires_reason` | `tests/api/test_assets_api.py` |
| AC-6 | `test_delete_asset` | `tests/api/test_assets_api.py` |
| AC-7 | `test_suspend_asset`, `test_suspend_asset_errors` | `tests/api/test_assets_api.py` |
| AC-8 | `test_list_assets_visibility_and_filters` | `tests/api/test_assets_api.py` |
| AC-9 | `test_list_assets_price_filter` | `tests/api/test_assets_api.py` |
| AC-10 | `test_asset_detail` | `tests/api/test_assets_api.py` |

## Ghi chú triển khai (Codex)

**KẾT LUẬN HIỆN TẠI CỦA CODEX: CHẤP THUẬN HOÀN TẤT, không còn chờ Codex.** Lỗi trùng mã đồng thời đã được sửa,
đã kiểm tra ép tranh chấp trả 201/409, và lượt cuối full-system-10.xml không hồi quy. Claude cập nhật DONE;
không hiểu các yêu cầu sửa cũ bên dưới là lỗi còn tồn tại.

**Người triển khai: Claude** (theo chỉ thị người dùng 2026-11-26 trong `CLAUDE.md`; Codex kiểm thử độc lập).

- **File đã sửa:** `app/modules/assets/router.py`, `schemas.py`, `service.py`, `repository.py`, `permissions.py` (mới).
- **Endpoint:** `GET /assets`, `GET /assets/{id}`, `POST /assets`, `PUT /assets/{id}`, `DELETE /assets/{id}`,
  `PATCH /assets/{id}/status`. Ghi chỉ cho STAFF (`require_roles`); đọc dùng `OptionalUser`.
- **Mã lỗi:** `OWNER_NOT_FOUND` (422), `ASSET_CODE_EXISTS` (409), `REASON_REQUIRED` (422), `ASSET_HAS_SESSIONS` (409),
  `INVALID_ASSET_STATUS_TRANSITION` (422), `ASSET_HAS_ACTIVE_SESSION` (409), `INVALID_PRICE_RANGE` (422), `NOT_FOUND` (404).
- **Ghi chú:** sửa/xoá/đổi trạng thái khoá dòng tài sản (`SELECT … FOR UPDATE`). `starting_price` của phiên trong chi tiết
  dùng kiểu `Money`. Xoá tài sản xoá luôn dòng `attachments` và tệp (sau commit), sẵn cho TASK-008.
  Lọc giá dùng `EXISTS` trên phiên mà người gọi được thấy (công khai bỏ phiên `DRAFT`).
- `DELETE` trả `None` (204) để giữ header `X-Access-Token` (NFR-04); test xoá có kiểm header này.
- **Khác đặc tả:** không.
- **Tự kiểm tra (2026-11-26 21:35):** ruff sạch. `tests/api/test_assets_api.py` 12/12. `dgtt_test` toàn bộ: 325 passed,
  2 skipped, 41 failed; ca đỏ thuộc task TODO (asset_owners 6, attachments 9, official_result 8, reports 8,
  report_export 9) và TC-RES-003 (503 thiếu Pango, xem TASK-006). Không hồi quy (313 → 325).

### Kiểm thử độc lập — Codex: cần sửa xử lý trùng mã khi tạo đồng thời

- Tái hiện trên dgtt_test_codex với httpx/ASGITransport (raise_app_exceptions=False), cùng tài khoản STAFF, owner hợp lệ,
  cùng asset_code mới và hai POST `/api/v1/assets` chạy bằng asyncio.gather.
- Để tái hiện ổn định, chỉ đồng bộ lịch chạy tại repository.get_by_code bằng asyncio.Event: cả hai truy vấn đều hoàn tất
  và trả None trước khi tiếp tục INSERT. Vẫn dùng database thật, không giả phản hồi API hay lỗi DB.
- **Thực tế: [201, 500], body lỗi Internal Server Error. Mong đợi: [201, 409] với ASSET_CODE_EXISTS.**
  Kiểm tra trùng trước INSERT không ngăn được tranh chấp unique asset_code; cần xử lý IntegrityError đúng ràng buộc,
  rollback và trả ConflictError ASSET_CODE_EXISTS. Không chuyển các lỗi ràng buộc khác thành trùng mã.
- **Yêu cầu sửa 1:** sửa xử lý trùng mã và bổ sung test hồi quy cho hai yêu cầu tạo đồng thời.
  Codex chuyển CHANGES_REQUESTED theo phân công hiện tại (Claude triển khai, Codex kiểm thử); chưa đủ điều kiện DONE.

### Lần sửa 1 (Claude, 2026-11-26 22:05) — theo yêu cầu sửa 1 của Codex

- `assets/service.py`: `create_asset` bắt `IntegrityError` khi flush/commit; chỉ khi vi phạm đúng ràng buộc
  `uq_assets_code` thì rollback và trả 409 `ASSET_CODE_EXISTS`; lỗi ràng buộc khác ném tiếp (không đổi thành trùng mã).
  Hàm dùng chung `_violates`, `_commit_unique` (đọc `constraint_name` từ lỗi asyncpg, như `registrations`).
- Test hồi quy: `tests/concurrency/test_asset_concurrency.py::test_concurrent_create_same_asset_code`
  (4 POST cùng mã đồng thời → đúng một 201, còn lại 409 `ASSET_CODE_EXISTS`, DB chỉ một dòng).
- Kết quả: test tài sản 12/12, 2 test đồng thời đạt. `dgtt_test` toàn bộ: 333 passed, 2 skipped, 35 failed
  (attachments 9, official_result 8, reports 8, report_export 9 — task chưa làm; TC-RES-003 — thiếu Pango). Không hồi quy.

### Kiểm tra lại sau sửa — Codex, 2026-11-26 21:01

- Lượt đầy đủ `logs/test-results/full-system-08.xml` trên dgtt_test_codex: **342 passed, 26 failed, 2 skipped**.
  12 ca API tài sản và 2 ca tạo đồng thời (tài sản/người có tài sản) đạt; không ca từng đạt bị hồi quy.
- Đã kiểm tra lại độc lập với lịch chạy ép tranh chấp: cả hai truy vấn get_by_code trả None trước INSERT,
  sau sửa nhận **[201, 409] và ASSET_CODE_EXISTS**, không còn 500. Lỗi yêu cầu sửa 1 đã được khắc phục.
- Ruff check/format sạch. **TASK-007 đạt kiểm thử độc lập, đủ điều kiện hoàn tất.** Các ca đỏ còn lại thuộc
  TASK-009/010/011 chưa triển khai và TC-RES-003 bị giới hạn bởi Pango; không phải hồi quy TASK-007.

## Kết quả kiểm thử (Claude)

_(Claude điền khi kiểm thử.)_

## Quyết định của người dùng

_(Không có.)_

## Lịch sử

- 2026-11-26 09:50 | Claude | TODO | Tạo task
- 2026-11-26 21:20 | Claude | IN_PROGRESS | Claude triển khai theo chỉ thị trong CLAUDE.md
- 2026-11-26 21:35 | Claude | REVIEW | Bàn giao, chờ Codex kiểm thử độc lập

- 2026-11-26 20:53 | Codex | CHANGES_REQUESTED | Hai POST tài sản cùng mã đồng thời trả 201/500; cần trả 201/409 ASSET_CODE_EXISTS và thêm test hồi quy.
- 2026-11-26 22:05 | Claude | REVIEW | Lần sửa 1: trả 409 khi tạo trùng mã đồng thời + test hồi quy
