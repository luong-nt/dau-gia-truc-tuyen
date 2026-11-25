# TASK-003: Tạo, sửa phiên đấu giá và xem lịch phiên công khai

- **Trạng thái:** DONE
- **FR/NFR liên quan:** FR-16, FR-08, FR-09, NFR-05, FR-26
- **Module:** `app/modules/sessions`
- **Phụ thuộc:** Không (không chung file với TASK-001/002, có thể làm song song)
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

Nhân viên tạo phiên đấu giá cho một tài sản (trạng thái `DRAFT`), phân công một đấu giá viên, đặt giá khởi điểm, bước giá,
tiền đặt trước, các mốc thời gian và nội dung thông báo. Sửa cấu hình được khi phiên chưa diễn ra; sau khi đã công khai,
mọi thay đổi phải có lý do và được ghi lại từng trường (FR-08: không âm thầm thay điều kiện đã công khai).
Khách xem danh sách và chi tiết phiên đã công khai mà không cần đăng nhập (FR-09).
(Endpoint công khai phiên `POST /sessions/{id}/publish` đã có sẵn.)

## Phạm vi file được sửa (Codex)

- `app/modules/sessions/router.py`
- `app/modules/sessions/schemas.py`
- `app/modules/sessions/service.py`
- `app/modules/sessions/repository.py`
- `app/core/deps.py`: **chỉ thêm** dependency `get_optional_user` / `OptionalUser` (token hợp lệ → User, không có token
  → `None`, token sai/hết hạn → 401). Không sửa phần đã có.

## Đặc tả API

### 1. `POST /api/v1/sessions`

- **Vai trò:** STAFF
- **Request JSON:** `asset_id`, `auctioneer_id`, `starting_price` (> 0, số nguyên), `bid_increment` (> 0, số nguyên),
  `deposit_amount` (≥ 0, số nguyên), `registration_deadline`, `deposit_deadline`, `start_time`, `end_time`
  (datetime UTC), `notice_content` (tuỳ chọn)
- **Response 201:** `SessionOut` (đã có trong `schemas.py`), `status = DRAFT`
- **Lỗi:**

| Tình huống | HTTP | `code` |
|---|---|---|
| Không phải STAFF | 403 | `FORBIDDEN` |
| Giá/tiền sai (≤ 0, số lẻ) | 422 | `VALIDATION_ERROR` |
| Tài sản không tồn tại | 404 | `NOT_FOUND` |
| Tài sản `ENDED` hoặc `SUSPENDED_CANCELLED` | 422 | `ASSET_NOT_AVAILABLE` |
| Tài sản đã có phiên khác chưa kết thúc (trạng thái khác `ENDED`, `CANCELLED`) | 409 | `ASSET_HAS_ACTIVE_SESSION` |
| `auctioneer_id` không phải user `AUCTIONEER` đang `ACTIVE` | 422 | `INVALID_AUCTIONEER` |
| Vi phạm mốc thời gian (quy tắc 2) | 422 | `INVALID_SCHEDULE` |

### 2. `PUT /api/v1/sessions/{session_id}`

- **Vai trò:** STAFF
- **Request JSON:** mọi trường của mục 1 **trừ** `asset_id`, đều tuỳ chọn (chỉ cập nhật trường được gửi),
  cộng thêm `reason` (string ≤ 500)
- **Response 200:** `SessionOut`
- **Lỗi:** như mục 1, cộng thêm:

| Tình huống | HTTP | `code` |
|---|---|---|
| Phiên không tồn tại | 404 | `NOT_FOUND` |
| Phiên `IN_PROGRESS`, `PAUSED`, `ENDED`, `CANCELLED` | 422 | `SESSION_LOCKED` |
| Phiên `OPEN_FOR_REGISTRATION` / `UPCOMING` mà thiếu `reason` | 422 | `REASON_REQUIRED` |

### 3. `GET /api/v1/sessions`  (công khai)

- **Vai trò:** không cần đăng nhập
- **Query:** `status` (tuỳ chọn), `keyword` (tìm trong mã/tên tài sản, tuỳ chọn), `page`, `size`
- **Response 200:** `Page[SessionPublicOut]`: các trường của `SessionOut` + `asset_code`, `asset_name`.
  **Không bao giờ** trả phiên `DRAFT`. Sắp xếp `start_time` tăng dần.

### 4. `GET /api/v1/sessions/manage`  (nội bộ)

- **Vai trò:** STAFF, ADMIN thấy mọi phiên, kể cả `DRAFT`; AUCTIONEER chỉ thấy phiên mình được phân công
- **Query, response:** như mục 3
- **Lưu ý:** khai báo route này **trước** `/{session_id}` để không bị nhầm thành `session_id = "manage"`.

### 5. `GET /api/v1/sessions/{session_id}`

- **Vai trò:** không cần đăng nhập (dùng `OptionalUser`)
- **Response 200:** `SessionPublicOut`
- **Lỗi:** 404 `NOT_FOUND` nếu không tồn tại, **hoặc** phiên `DRAFT` mà người gọi không phải STAFF/ADMIN/đấu giá viên
  được phân công (không để lộ sự tồn tại của bản nháp).

## Quy tắc nghiệp vụ

1. Phiên mới: `status = DRAFT`.
2. **Mốc thời gian** (kiểm tra cả khi tạo và khi sửa, trên giá trị **sau khi** gộp thay đổi):
   - `registration_deadline < start_time`
   - `deposit_deadline < start_time`
   - `start_time < end_time`
   - Khi tạo, hoặc khi đổi `start_time`: `start_time > utcnow()`

   Kiểm tra ở service để trả `INVALID_SCHEDULE` tiếng Việt **trước khi** DB báo lỗi CHECK.
3. Sửa ở `DRAFT`: không cần lý do. Sửa ở `OPEN_FOR_REGISTRATION`/`UPCOMING`: bắt buộc `reason`; với **mỗi** trường thay đổi
   ghi một dòng `activity_logs` (`action = "UPDATE_SESSION"`, `entity_type = "auction_session"`, `field_name`, `old_value`,
   `new_value`, `reason`). Ở `DRAFT` cũng ghi các dòng đó, chỉ khác là `reason` có thể rỗng.
4. Tạo phiên: `activity_logs` `action = "CREATE_SESSION"`, `user_id` = nhân viên (đây là nguồn "người tạo phiên"
   như comment trong SQL).
5. Đổi `auctioneer_id` cũng phải qua kiểm tra `INVALID_AUCTIONEER`.
6. Tiền: kiểu `Decimal`, chỉ chấp nhận số nguyên (`numeric(18,0)`).

## Tiêu chí chấp nhận

- **AC-1:** STAFF tạo phiên hợp lệ → 201 `DRAFT`, `code = "PDG-<id>"`, có log `CREATE_SESSION`.
- **AC-2:** Mỗi lỗi trong bảng mục 1 trả đúng HTTP + `code`; không tạo dòng `auction_sessions` khi lỗi.
- **AC-3:** Sửa phiên `DRAFT` không cần lý do; mỗi trường đổi có một log `UPDATE_SESSION` với `old_value`/`new_value`.
- **AC-4:** Sửa phiên `OPEN_FOR_REGISTRATION` thiếu lý do → `REASON_REQUIRED`; có lý do → thành công, log có `reason`.
- **AC-5:** Sửa phiên `IN_PROGRESS` → `SESSION_LOCKED`.
- **AC-6:** Sửa làm sai mốc thời gian (ví dụ `end_time` trước `start_time`) → `INVALID_SCHEDULE`, dữ liệu không đổi.
- **AC-7:** `GET /sessions` không cần token, không chứa phiên `DRAFT`; lọc `status`, `keyword` đúng; có phân trang.
- **AC-8:** `GET /sessions/manage`: STAFF thấy cả `DRAFT`; AUCTIONEER chỉ thấy phiên của mình; BIDDER → 403; không token → 401.
- **AC-9:** `GET /sessions/{id}` của phiên `DRAFT`: khách → 404; STAFF → 200. Token sai → 401.
- **AC-10:** BIDDER/AUCTIONEER gọi `POST`/`PUT` → 403.

## Kế hoạch kiểm thử (Claude)

| AC | File |
|---|---|
| AC-1 … AC-10 | `tests/api/test_sessions_api.py` |

## Ghi chú triển khai (Codex)

- Sửa 4 file router/schemas/service/repository của sessions và chỉ thêm `get_optional_user`/`OptionalUser` vào `app/core/deps.py` như phạm vi được phép.
- Đã hiện thực POST/GET `/api/v1/sessions`, PUT/GET `/api/v1/sessions/{session_id}`, GET `/api/v1/sessions/manage`. Route manage khai báo trước route tham số.
- Kiểm tra tài sản, đấu giá viên ACTIVE, tiền Decimal nguyên tối đa 18 chữ số, lịch sau gộp thay đổi; datetime có múi giờ được đổi về UTC không múi giờ trước khi lưu.
- Khóa dòng tài sản khi tạo để tránh tạo đồng thời hai phiên chưa kết thúc; sửa khóa dòng phiên. Sau công khai bắt buộc lý do, ghi log từng trường đổi. API công khai luôn ẩn DRAFT; nội bộ áp dụng vai trò và đấu giá viên phụ trách.
- Mã lỗi: NOT_FOUND, ASSET_NOT_AVAILABLE, ASSET_HAS_ACTIVE_SESSION, INVALID_AUCTIONEER, INVALID_SCHEDULE, SESSION_LOCKED, REASON_REQUIRED, VALIDATION_ERROR; UNAUTHORIZED/TOKEN_EXPIRED/FORBIDDEN qua dependency. Không đổi đặc tả.
- Ruff check/format sạch. Không DB: 38 passed, 121 skipped. Toàn bộ test trên dgtt_test_codex: 158 passed, 1 failed do test dựng dữ liệu sai trước khi gọi API.
- Test cần Claude sửa: `tests/api/test_sessions_api.py::test_create_validation_error[missing-asset-id]`, dòng 246 gọi `_payload(sc.asset.asset_id, ..., **{'asset_id': None})` gây TypeError multiple values for argument asset_id. Codex không sửa tests theo phân công. Đã gọi API thiếu asset_id bằng httpx trên dev và xác nhận 422 VALIDATION_ERROR.
- Cách thử nhanh: khách GET `/api/v1/sessions` và chi tiết phiên trả 200; staff đăng nhập và GET `/api/v1/sessions/manage` trả 200; chi tiết với Bearer invalid trả 401. Đã kiểm tra trên dev dgtt.

## Kết quả kiểm thử (Claude)

**Thời điểm:** 2026-11-25 21:50 (giờ Việt Nam) · **Kết luận:** DONE

**Lệnh đã chạy:**

| Lệnh | Kết quả |
|---|---|
| `ruff check .` · `ruff format --check .` | Sạch (101 file) |
| `pytest` (không DB) | 38 đạt, 121 bỏ qua (cần DB) |
| `TEST_DATABASE_URL=…/dgtt_test pytest` (toàn bộ) | **159/159 đạt**, không hồi quy |
| Riêng TASK-003 (`test_sessions_api.py`) + `test_state_machine.py` | 88/88 đạt |

**Về test đỏ Codex báo** (`test_create_validation_error[missing-asset-id]`): lỗi nằm ở test của Claude (truyền `asset_id`
hai lần vào `_payload`). Claude đã sửa test ngay lượt 2026-11-25 21:35; Codex không cần làm gì.

**Tiêu chí chấp nhận:**

| AC | Kết quả | Test |
|---|---|---|
| AC-1 | Đạt | `test_create_session_success`, `test_create_session_minimal_and_zero_deposit`, `test_create_allowed_when_old_session_finished` |
| AC-2 | Đạt | `test_create_validation_error`, `test_create_unknown_asset`, `test_create_asset_not_available`, `test_create_asset_has_active_session`, `test_create_invalid_auctioneer`, `test_create_invalid_schedule` |
| AC-3 | Đạt | `test_update_draft_without_reason`, `test_update_logs_only_changed_fields` |
| AC-4 | Đạt | `test_update_published_requires_reason`, `test_update_published_with_reason` |
| AC-5 | Đạt | `test_update_locked_session` (IN_PROGRESS, PAUSED, ENDED, CANCELLED) |
| AC-6 | Đạt | `test_update_invalid_schedule` |
| AC-7 | Đạt | `test_public_list_excludes_draft`, `test_public_list_status_filter`, `test_public_list_keyword_and_pagination` |
| AC-8 | Đạt | `test_manage_list_staff_admin_see_all`, `test_manage_list_auctioneer_sees_only_own`, `test_manage_list_bidder_forbidden`, `test_manage_without_token_returns_401` |
| AC-9 | Đạt | `test_detail_draft_visibility`, `test_detail_public_session_for_guest`, `test_detail_unknown_session`, `test_detail_with_bad_token_returns_401` |
| AC-10 | Đạt | `test_create_requires_staff`, `test_update_requires_staff`, `test_create/update_without_token_returns_401` |
| Quy tắc 5 | Đạt | `test_update_invalid_auctioneer` |

**Kiểm tra thêm bằng request thủ công (test tạm, đã xoá):** số `100000000.0` → 201; datetime có múi giờ `+07:00` được
đổi đúng về UTC; `starting_price: null` khi sửa → 422 `VALIDATION_ERROR`; số 19 chữ số → 422; `reason` chỉ toàn khoảng
trắng → 422 `REASON_REQUIRED`; body rỗng `{}` → 200, không đổi gì.

**Review code (AGENTS.md Mục 4):**

- Chia lớp đúng; `commit` trong service; truy vấn trong `repository.py`; route `/manage` khai báo trước `/{session_id}`.
- Tạo phiên khóa dòng tài sản (`get_asset_for_update`) → chặn được hai request tạo phiên đồng thời cho cùng tài sản.
  Sửa phiên khóa dòng phiên bằng `get_session_for_update`.
- `log_activity` (`CREATE_SESSION`, `UPDATE_SESSION` từng trường, kèm `reason`) trước `commit`; chỉ ghi trường thực sự đổi.
- Mốc thời gian kiểm tra trên giá trị sau khi gộp; chỉ ép `start_time > utcnow()` khi tạo hoặc khi đổi `start_time`.
- Dùng `utcnow()`, enum, lớp lỗi chuẩn. `get_optional_user` chỉ thêm mới, không sửa phần cũ của `deps.py`.
- Không lộ dữ liệu định danh (phiên/tài sản không chứa trường định danh).

**Ghi chú nhỏ (không chặn DONE):**

- `keyword` còn khớp mã phiên `PDG-<id>` (ngoài đặc tả "mã/tên tài sản"). Tiện cho người dùng, nhưng `keyword=PDG`
  sẽ khớp mọi phiên. Giữ nguyên; nếu nhóm muốn bỏ thì sửa trong task sau.
- `SessionCreateRequest` kế thừa trường `reason` từ `SessionUpdateRequest`: khi tạo, `reason` được nhận rồi bỏ qua.
- `PUT` với `notice_content: null` xoá nội dung thông báo (có ghi log). Phù hợp đặc tả vì trường này tuỳ chọn.
- Sửa phiên chưa phát sự kiện realtime cho người đang xem lịch phiên; đặc tả chưa yêu cầu (có thể làm cùng FR-08 thông báo).

## Quyết định của người dùng

_(Trống.)_

## Lịch sử

- 2026-11-25 20:40 | Claude | TODO | Tạo task

- 2026-11-25 21:26 | Codex | IN_PROGRESS | Nhận TASK-003, tạo/sửa và tra cứu phiên theo đặc tả.

- 2026-11-25 21:29 | Codex | REVIEW | Bàn giao TASK-003; 158 test đạt, 1 test lỗi dựng payload; API dev và lint/format đạt.

- 2026-11-25 21:43 | Claude | TESTING | Nhận kiểm thử TASK-003.

- 2026-11-25 21:50 | Claude | DONE | 159/159 test đạt trên dgtt_test; mọi AC đạt.
