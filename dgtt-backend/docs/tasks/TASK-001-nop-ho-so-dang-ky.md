# TASK-001: Nộp hồ sơ đăng ký tham gia phiên và xem hồ sơ của tôi

- **Trạng thái:** DONE
- **FR/NFR liên quan:** FR-10, FR-13 (phần người tham gia), NFR-05, FR-26
- **Module:** `app/modules/registrations`
- **Phụ thuộc:** Không
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

Người tham gia (BIDDER) nộp hồ sơ đăng ký cho một phiên đang nhận hồ sơ, kèm giấy tờ định danh và (tuỳ chọn) chứng từ
nộp tiền đặt trước. Hệ thống lưu bản thông tin đã gửi (`submitted_*`), lưu tệp vào `attachments`, đặt trạng thái
`PENDING`. Người tham gia xem lại danh sách hồ sơ của mình, trạng thái, hạn bổ sung và lịch sử phản hồi, và tải lại
tệp của chính mình.

## Phạm vi file được sửa (Codex)

- `app/modules/registrations/router.py`
- `app/modules/registrations/schemas.py`
- `app/modules/registrations/service.py`
- `app/modules/registrations/repository.py`
- `app/modules/registrations/permissions.py`

(Router đã được gắn trong `app/main.py` với prefix `/api/v1`, không cần sửa.)

## Đặc tả API

### 1. `POST /api/v1/sessions/{session_id}/registrations`

- **Vai trò:** BIDDER
- **Request:** `multipart/form-data`

| Trường | Kiểu | Bắt buộc | Ràng buộc |
|---|---|---|---|
| `submitted_full_name` | text | Có | 1–100 ký tự, bỏ khoảng trắng đầu/cuối |
| `submitted_id_number` | text | Có | 9–20 ký tự, chỉ chữ số |
| `submitted_address` | text | Không | ≤ 255 ký tự |
| `submitted_phone` | text | Không | `^[0-9+]{9,15}$` |
| `identity_documents` | file (nhiều) | Có, ≥ 1 tệp | pdf/jpg/jpeg/png, mỗi tệp ≤ `MAX_UPLOAD_MB` |
| `deposit_receipt` | file | Không | pdf/jpg/jpeg/png, ≤ `MAX_UPLOAD_MB` |

- **Response 201:** `RegistrationDetailOut`

```json
{
  "registration_id": 1, "session_id": 3, "session_code": "PDG-3",
  "submitted_full_name": "...", "submitted_id_number": "...", "submitted_address": null, "submitted_phone": null,
  "submission_count": 1, "status": "PENDING", "supplement_deadline": null, "bidder_alias": null,
  "submitted_at": "2026-11-25T13:00:00",
  "attachments": [
    {"attachment_id": 10, "file_type": "IDENTITY_DOCUMENT", "file_name": "cccd.pdf", "file_format": "pdf",
     "file_size": 12345, "submission_no": 1, "uploaded_at": "..."}
  ],
  "reviews": []
}
```

- **Lỗi:**

| Tình huống | HTTP | `code` |
|---|---|---|
| Chưa đăng nhập | 401 | `UNAUTHORIZED` |
| Không phải BIDDER | 403 | `FORBIDDEN` |
| Phiên không tồn tại | 404 | `NOT_FOUND` |
| Phiên không ở `OPEN_FOR_REGISTRATION`, hoặc `utcnow() >= registration_deadline` | 422 | `REGISTRATION_CLOSED` |
| Đã có hồ sơ cho phiên này (bất kể trạng thái) | 409 | `ALREADY_REGISTERED` |
| Thiếu trường bắt buộc / sai định dạng trường text | 422 | `VALIDATION_ERROR` |
| Không có tệp `identity_documents` nào | 422 | `IDENTITY_DOCUMENT_REQUIRED` |
| Tệp sai định dạng hoặc quá dung lượng | 422 | `BUSINESS_RULE_VIOLATION` (do `save_upload` ném) |

### 2. `GET /api/v1/registrations/me`

- **Vai trò:** BIDDER
- **Query:** `status` (tuỳ chọn, một giá trị của `RegistrationStatus`), phân trang `page`, `size`
- **Response 200:** `Page[RegistrationDetailOut]` — chỉ hồ sơ của người đang đăng nhập, mới nhất trước.
  `reviews` gồm các dòng `registration_reviews` của hồ sơ, **chỉ** các trường `review_type`, `result`, `reason`,
  `reviewed_at` (ẩn `reviewed_by` và `evidence`), cũ nhất trước.

### 3. `GET /api/v1/registrations/{registration_id}/attachments/{attachment_id}`

- **Vai trò:** chủ hồ sơ (BIDDER) hoặc STAFF
- **Response 200:** nội dung tệp (`FileResponse`, `filename` = tên gốc)
- **Lỗi:** 401; 403 `FORBIDDEN` nếu không phải chủ hồ sơ và không phải STAFF;
  404 `NOT_FOUND` nếu hồ sơ không tồn tại, hoặc tệp không thuộc hồ sơ đó.

## Quy tắc nghiệp vụ

1. Kiểm tra theo thứ tự: phiên tồn tại → phiên đang nhận hồ sơ → chưa có hồ sơ → có giấy tờ → lưu.
2. Bản ghi mới: `status = PENDING`, `submission_count = 1`, `bidder_id` = người đăng nhập.
3. Mỗi tệp lưu bằng `save_upload(file, subdir=f"registrations/{registration_id}")` và tạo một dòng `attachments`
   với `registration_id`, `submission_no = 1`, `file_type` = `IDENTITY_DOCUMENT` hoặc `DEPOSIT_RECEIPT`,
   `display_order` tăng dần từ 1; `asset_id = NULL`.
4. Nếu có lỗi sau khi đã lưu một phần tệp: rollback DB và xoá các tệp đã lưu của lần nộp này (best effort).
5. Hai request nộp đồng thời của cùng một người cho cùng phiên: chỉ một thành công, request còn lại trả 409
   `ALREADY_REGISTERED` (bắt `IntegrityError` của `uq_registrations_session_bidder`, không để lộ lỗi 500).
6. Ghi `activity_logs`: `action = "SUBMIT_REGISTRATION"`, `entity_type = "registration"`, `entity_id = registration_id`,
   `user_id` = người nộp.
7. Thay đổi thông tin tài khoản (FR-03) **không** ảnh hưởng các trường `submitted_*` đã lưu.

## Tiêu chí chấp nhận

- **AC-1:** BIDDER nộp hồ sơ hợp lệ cho phiên `OPEN_FOR_REGISTRATION` còn hạn → 201, DB có 1 `registrations` PENDING,
  `submission_count = 1`, đúng số dòng `attachments` với `submission_no = 1` và đúng `file_type`; tệp tồn tại trong `storage/`.
- **AC-2:** Phiên ở trạng thái khác `OPEN_FOR_REGISTRATION` (ví dụ `DRAFT`, `UPCOMING`, `IN_PROGRESS`) → 422 `REGISTRATION_CLOSED`.
- **AC-3:** Phiên `OPEN_FOR_REGISTRATION` nhưng đã qua `registration_deadline` → 422 `REGISTRATION_CLOSED`.
- **AC-4:** Nộp lần hai cho cùng phiên → 409 `ALREADY_REGISTERED`, không tạo thêm dòng `registrations`/`attachments`.
- **AC-5:** Không gửi `identity_documents` → 422 `IDENTITY_DOCUMENT_REQUIRED`, không tạo dòng nào.
- **AC-6:** Tệp `.exe` hoặc tệp lớn hơn `MAX_UPLOAD_MB` → 422, không tạo dòng `registrations`.
- **AC-7:** Không token → 401; STAFF/ADMIN/AUCTIONEER gọi API nộp → 403.
- **AC-8:** Có dòng `activity_logs` `SUBMIT_REGISTRATION` đúng `entity_id` và `user_id`.
- **AC-9:** `GET /registrations/me` chỉ trả hồ sơ của chính người gọi (không thấy hồ sơ người khác); lọc `status` đúng;
  `reviews` không có trường `reviewed_by`, `evidence`.
- **AC-10:** Chủ hồ sơ và STAFF tải được tệp; BIDDER khác → 403; `attachment_id` thuộc hồ sơ khác → 404.
- **AC-11:** Phiên không tồn tại → 404.

## Kế hoạch kiểm thử (Claude)

| AC | Test | File |
|---|---|---|
| AC-1, AC-8 | `test_submit_registration_success` | `tests/api/test_registrations_api.py` |
| AC-2, AC-3, AC-11 | `test_submit_when_session_not_open`, `test_submit_after_deadline`, `test_submit_unknown_session` | như trên |
| AC-4 | `test_submit_duplicate` | như trên |
| AC-5, AC-6 | `test_submit_without_identity_document`, `test_submit_bad_file` | như trên |
| AC-7 | `test_submit_requires_bidder` | như trên |
| AC-9 | `test_my_registrations_only_own` | như trên |
| AC-10 | `test_download_attachment_permissions` | như trên |
| Quy tắc 5 | `test_concurrent_duplicate_submit` | `tests/concurrency/test_registration_concurrency.py` |

Dữ liệu: Claude tạo phiên `OPEN_FOR_REGISTRATION` trong `tests/factories.py`.

## Ghi chú triển khai (Codex)

- Hoàn thiện router, schemas, service, repository, permissions trong `app/modules/registrations/`; sửa định dạng router khi tiếp tục lượt dở.
- Endpoint: POST `/api/v1/sessions/{session_id}/registrations`, GET `/api/v1/registrations/me`, GET `/api/v1/registrations/{registration_id}/attachments/{attachment_id}`.
- Mã lỗi: NOT_FOUND, FORBIDDEN, REGISTRATION_CLOSED, ALREADY_REGISTERED, IDENTITY_DOCUMENT_REQUIRED; VALIDATION_ERROR qua DTO, BUSINESS_RULE_VIOLATION qua save_upload.
- Khóa dòng phiên trước khi nộp; bắt ràng buộc trùng; rollback và dọn tệp khi lỗi. Bản thông tin nộp độc lập tài khoản; phản hồi ẩn reviewed_by/evidence.
- Không khác đặc tả. Ruff check/format sạch. Không DB: 34 passed, 53 skipped; toàn bộ test trên dgtt_test_codex: 87 passed, gồm API và concurrency của Claude, không còn test đỏ.
- Thử nhanh bằng httpx trên dgtt: đăng nhập bidder1 trả 200, GET `/api/v1/registrations/me` trả 200 (total=1).
- Dev DB ban đầu chưa có bảng: đã chạy migration chuẩn và seed. Seed commit thành công nhưng in thông báo gặp encoding console Windows; API dev xác nhận dữ liệu dùng được.

## Kết quả kiểm thử (Claude)

**Thời điểm:** 2026-11-25 21:40 (giờ Việt Nam) · **Kết luận:** DONE

**Lệnh đã chạy:**

| Lệnh | Kết quả |
|---|---|
| `ruff check .` · `ruff format --check .` | Sạch (101 file) |
| `pytest` (không DB) | 38 đạt, 121 bỏ qua (cần DB) |
| `TEST_DATABASE_URL=…/dgtt_test pytest` (toàn bộ) | **159/159 đạt**, không hồi quy |
| Riêng TASK-001 (`test_registrations_api.py`, `test_registration_concurrency.py`) | 46/46 đạt |

**Tiêu chí chấp nhận:**

| AC | Kết quả | Test |
|---|---|---|
| AC-1 | Đạt | `test_submit_registration_success`, `test_submit_minimal_fields` |
| AC-2 | Đạt | `test_submit_when_session_not_open` |
| AC-3 | Đạt | `test_submit_after_deadline` |
| AC-4 | Đạt | `test_submit_duplicate`, `test_submit_duplicate_any_status` |
| AC-5 | Đạt | `test_submit_without_identity_document`, `test_submit_check_order_closed_before_documents` |
| AC-6 | Đạt | `test_submit_bad_file`, `test_submit_file_too_large` |
| AC-7 | Đạt | `test_submit_without_token_returns_401`, `test_submit_requires_bidder`, `test_my_registrations_requires_bidder` |
| AC-8 | Đạt | `test_submit_registration_success` |
| AC-9 | Đạt | `test_my_registrations_only_own` |
| AC-10 | Đạt | `test_download_attachment_permissions`, `test_download_attachment_without_token_returns_401` |
| AC-11 | Đạt | `test_submit_unknown_session` |
| Quy tắc 5 | Đạt | `test_concurrent_duplicate_submit` |

**Review code (AGENTS.md Mục 4):**

- Chia lớp đúng: router chỉ gọi service; truy vấn trong `repository.py`; `commit` trong service.
- Khóa dòng phiên bằng `sessions.repository.get_session_for_update` trước khi kiểm tra trùng → đúng Mục 4.10.
- `log_activity("SUBMIT_REGISTRATION")` trước `commit`, cùng transaction. Không có broadcast (không cần).
- Dùng `utcnow()`; enum từ `app/db/enums.py`; lỗi qua `app/core/exceptions.py` với `code` đúng đặc tả.
- Bắt `IntegrityError` theo đúng tên ràng buộc `uq_registrations_session_bidder` → 409, không lộ 500.
- Rollback + dọn tệp khi lỗi; tệp chỉ lưu qua `save_upload`, tải về qua `resolve_path` sau khi kiểm tra quyền.
- `ReviewOut` ẩn `reviewed_by`, `evidence`. `submitted_id_number` chỉ trả cho chính chủ hồ sơ → phù hợp Mục 5.11.

**Ghi chú nhỏ (không chặn DONE):**

- `submitted_address` không bỏ khoảng trắng đầu/cuối và chuỗi rỗng được lưu là `""` thay vì `NULL`. Đặc tả không yêu cầu,
  có thể chuẩn hoá khi làm TASK-002 (nộp lại hồ sơ dùng chung schema).
- `except BaseException` trong `submit_registration` có bắt cả `CancelledError`, nhưng luôn `raise` lại nên chấp nhận được.

## Quyết định của người dùng

_(Trống.)_

## Lịch sử

- 2026-11-25 20:40 | Claude | TODO | Tạo task

- 2026-11-25 20:44 | Codex | IN_PROGRESS | Nhận TASK-001, hiện thực nộp hồ sơ và tra cứu/tải tệp của người tham gia.

- 2026-11-25 21:25 | Codex | REVIEW | Bàn giao TASK-001; 87 test đạt, lint/format sạch, API dev 200.

- 2026-11-25 21:38 | Claude | TESTING | Nhận kiểm thử TASK-001.

- 2026-11-25 21:40 | Claude | DONE | 159/159 test đạt trên dgtt_test; mọi AC đạt.
