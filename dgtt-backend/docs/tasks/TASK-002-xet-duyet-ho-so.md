# TASK-002: Đối chiếu, xét duyệt, yêu cầu bổ sung và nộp lại hồ sơ

- **Trạng thái:** DONE
- **FR/NFR liên quan:** FR-11, FR-12, FR-13 (phần nhân viên), NFR-05, FR-26
- **Module:** `app/modules/registrations`
- **Phụ thuộc:** TASK-001 (cùng module, cùng file; làm sau khi TASK-001 DONE)
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

Nhân viên (STAFF) tra cứu hồ sơ, ghi kết quả từng bước đối chiếu (giấy tờ, điều kiện, tiền đặt trước), rồi ra quyết định:
duyệt, yêu cầu bổ sung (có hạn) hoặc từ chối. Khi duyệt, hệ thống cấp mã ẩn danh `bidder_alias`. Người tham gia có hồ sơ
bị yêu cầu bổ sung thì nộp lại trước hạn; hồ sơ quay về `PENDING`. Mọi bước được lưu vào `registration_reviews`
và `activity_logs`.

## Phạm vi file được sửa (Codex)

- `app/modules/registrations/router.py`
- `app/modules/registrations/schemas.py`
- `app/modules/registrations/service.py`
- `app/modules/registrations/repository.py`
- `app/modules/registrations/permissions.py`

## Đặc tả API

### 1. `GET /api/v1/registrations`

- **Vai trò:** STAFF
- **Query:** `session_id` (tuỳ chọn), `status` (tuỳ chọn), `keyword` (tìm trong họ tên hoặc số giấy tờ, tuỳ chọn), `page`, `size`
- **Response 200:** `Page[RegistrationDetailOut]`. Với STAFF, `reviews` có đủ `reviewed_by`, `evidence`.

### 2. `GET /api/v1/registrations/{registration_id}`

- **Vai trò:** chủ hồ sơ hoặc STAFF
- **Response 200:** `RegistrationDetailOut`; chủ hồ sơ thấy `reviews` rút gọn như TASK-001.
- **Lỗi:** 401, 403 `FORBIDDEN`, 404 `NOT_FOUND`

### 3. `POST /api/v1/registrations/{registration_id}/checks`

- **Vai trò:** STAFF
- **Request JSON:**

| Trường | Kiểu | Bắt buộc | Ràng buộc |
|---|---|---|---|
| `review_type` | string | Có | `DOCUMENT_CHECK` \| `ELIGIBILITY_CHECK` \| `DEPOSIT_CHECK` |
| `result` | string | Có | `PASSED` \| `FAILED` |
| `reason` | string | Khi `FAILED` | ≤ 500 |
| `evidence` | string | Không | ≤ 500 (căn cứ: số chứng từ ngân hàng, ghi chú đối chiếu…) |

- **Response 201:** `ReviewOut` (đủ trường)
- **Lỗi:**

| Tình huống | HTTP | `code` |
|---|---|---|
| Hồ sơ không ở `PENDING` | 422 | `INVALID_REGISTRATION_STATUS` |
| `FAILED` mà thiếu `reason` | 422 | `REASON_REQUIRED` |
| `review_type` không thuộc 3 loại trên | 422 | `VALIDATION_ERROR` |

### 4. `POST /api/v1/registrations/{registration_id}/decision`

- **Vai trò:** STAFF
- **Request JSON:** `decision` (`APPROVE` \| `REQUEST_SUPPLEMENT` \| `REJECT`), `reason` (string ≤ 500),
  `supplement_deadline` (datetime UTC, chỉ dùng khi `REQUEST_SUPPLEMENT`)
- **Response 200:** `RegistrationDetailOut` sau khi cập nhật
- **Lỗi:**

| Tình huống | HTTP | `code` |
|---|---|---|
| Hồ sơ không ở `PENDING` | 422 | `INVALID_REGISTRATION_STATUS` |
| Phiên đã `IN_PROGRESS`, `PAUSED`, `ENDED` hoặc `CANCELLED` | 422 | `SESSION_NOT_ACCEPTING_REVIEWS` |
| `APPROVE` khi 3 bước kiểm tra mới nhất chưa cùng `PASSED` | 422 | `CHECKS_NOT_PASSED` (`details` = kết quả từng bước) |
| `REQUEST_SUPPLEMENT` / `REJECT` thiếu `reason` | 422 | `REASON_REQUIRED` |
| `REQUEST_SUPPLEMENT` thiếu hạn, hạn ≤ `utcnow()`, hoặc hạn ≥ `start_time` của phiên | 422 | `INVALID_SUPPLEMENT_DEADLINE` |

### 5. `PUT /api/v1/registrations/{registration_id}`  (nộp lại)

- **Vai trò:** chủ hồ sơ (BIDDER)
- **Request:** `multipart/form-data`, các trường text như TASK-001 nhưng **đều tuỳ chọn** (chỉ cập nhật trường được gửi),
  `identity_documents` (0..n tệp), `deposit_receipt` (0..1 tệp). Phải có ít nhất một trường text hoặc một tệp.
- **Response 200:** `RegistrationDetailOut`
- **Lỗi:**

| Tình huống | HTTP | `code` |
|---|---|---|
| Không phải chủ hồ sơ | 403 | `FORBIDDEN` |
| Hồ sơ không ở `NEEDS_SUPPLEMENT` | 422 | `INVALID_REGISTRATION_STATUS` |
| `utcnow() >= supplement_deadline` | 422 | `SUPPLEMENT_EXPIRED` |
| Không gửi gì để bổ sung | 422 | `NOTHING_TO_UPDATE` |

## Quy tắc nghiệp vụ

1. Mỗi lần gọi `checks` hoặc `decision` thêm **một** dòng `registration_reviews` (`reviewed_by` = nhân viên,
   `reviewed_at` mặc định). Với `decision`: `review_type` = `APPROVE` / `REQUEST_SUPPLEMENT` / `REJECT`,
   `result = NULL`.
2. `APPROVE` dùng `repository.latest_check_results` + `all_checks_passed` (kết quả **mới nhất** của từng loại).
3. Cấp `bidder_alias`: **khóa dòng phiên** bằng `sessions.repository.get_session_for_update`, rồi
   `format_alias(next_alias_number(session_id))`. Hai lần duyệt đồng thời trong cùng phiên không được trùng mã.
4. `REQUEST_SUPPLEMENT`: đặt `status = NEEDS_SUPPLEMENT`, `supplement_deadline`. `REJECT`: `status = REJECTED`.
5. Nộp lại: `submission_count += 1`; các tệp mới có `submission_no` = giá trị `submission_count` mới; tệp cũ giữ nguyên
   (không xoá, để lưu lịch sử từng lần nộp); cập nhật các trường `submitted_*` được gửi; `status = PENDING`;
   `supplement_deadline` giữ nguyên giá trị cũ để tra cứu.
6. Hồ sơ quá hạn bổ sung: **không** tự đổi trạng thái (AGENTS.md Mục 5.4). Nhân viên có thể từ chối thủ công:
   cho phép `decision = REJECT` với hồ sơ `NEEDS_SUPPLEMENT` **đã quá hạn** (ngoại lệ duy nhất của quy tắc "chỉ từ PENDING").
7. `activity_logs` (`entity_type = "registration"`), ghi `field_name = "status"` với `old_value`/`new_value` khi đổi trạng thái:
   - `checks`: `action` = `CHECK_DOCUMENT` / `CHECK_ELIGIBILITY` / `CONFIRM_DEPOSIT` (DEPOSIT_CHECK), `new_value` = kết quả
   - `decision`: `APPROVE_REGISTRATION` / `REQUEST_SUPPLEMENT` / `REJECT_REGISTRATION`, `reason` = lý do
   - nộp lại: `RESUBMIT_REGISTRATION`

## Tiêu chí chấp nhận

- **AC-1:** STAFF lọc danh sách theo `session_id`, `status`, `keyword` đúng; có phân trang; BIDDER gọi → 403.
- **AC-2:** Ghi 3 bước `PASSED` rồi `APPROVE` → `APPROVED`, có `bidder_alias` dạng `NTG-01`; hồ sơ duyệt tiếp theo
  trong cùng phiên nhận `NTG-02`.
- **AC-3:** `APPROVE` khi thiếu một bước, hoặc bước mới nhất là `FAILED` (dù trước đó `PASSED`) → 422 `CHECKS_NOT_PASSED`.
  Ngược lại: `FAILED` rồi ghi lại `PASSED` → duyệt được.
- **AC-4:** `checks` với `FAILED` thiếu `reason` → 422 `REASON_REQUIRED`.
- **AC-5:** `REQUEST_SUPPLEMENT` hợp lệ → `NEEDS_SUPPLEMENT` + hạn; thiếu lý do → `REASON_REQUIRED`;
  hạn sai → `INVALID_SUPPLEMENT_DEADLINE`.
- **AC-6:** `REJECT` thiếu lý do → `REASON_REQUIRED`; có lý do → `REJECTED`.
- **AC-7:** Quyết định trên hồ sơ không ở `PENDING` → 422 `INVALID_REGISTRATION_STATUS` (trừ quy tắc 6).
- **AC-8:** Nộp lại trước hạn → `PENDING`, `submission_count = 2`, tệp mới có `submission_no = 2`, tệp cũ còn nguyên.
- **AC-9:** Nộp lại sau hạn → 422 `SUPPLEMENT_EXPIRED`; nộp lại khi hồ sơ `PENDING` → `INVALID_REGISTRATION_STATUS`;
  người khác nộp lại → 403.
- **AC-10:** Nhân viên `REJECT` được hồ sơ `NEEDS_SUPPLEMENT` đã quá hạn.
- **AC-11:** Mỗi bước ở trên có đúng một dòng `registration_reviews` và một dòng `activity_logs` với `action` như quy tắc 7.
- **AC-12:** Chủ hồ sơ xem chi tiết thấy `reviews` không có `reviewed_by`, `evidence`; BIDDER khác → 403.
- **AC-13:** Duyệt đồng thời 10 hồ sơ của cùng một phiên → 10 mã `NTG-01`…`NTG-10` không trùng, không lỗi 500.

## Kế hoạch kiểm thử (Claude)

| AC | File |
|---|---|
| AC-1 … AC-12 | `tests/api/test_registration_review_api.py` |
| AC-13 | `tests/concurrency/test_registration_concurrency.py` |

## Ghi chú triển khai (Codex)

- Sửa router, schemas, service, repository của `app/modules/registrations/`; dùng permissions sẵn có. Hoàn thành GET danh sách/chi tiết, POST checks/decision và PUT nộp lại theo đặc tả.
- Thêm DTO checks/decision/nộp bổ sung, StaffReviewOut chứa người kiểm tra và căn cứ; DTO trả cho chủ hồ sơ vẫn loại bỏ các trường nội bộ. Chuẩn hóa deadline có múi giờ về UTC không múi giờ.
- Khóa theo thứ tự phiên rồi hồ sơ; đọc lại hồ sơ sau khóa để không dùng trạng thái cũ. Duyệt dùng kết quả mới nhất của đủ 3 bước, cấp mã dưới khóa phiên. Ghi đúng review, audit và trạng thái trong cùng transaction.
- Nộp lại kiểm tra chủ hồ sơ, trạng thái, hạn và nội dung; tăng submission_count, lưu tệp mới với số lần nộp mới, giữ tệp cũ và supplement_deadline. Lỗi rollback và dọn tệp lần nộp mới. Cho phép từ chối thủ công NEEDS_SUPPLEMENT quá hạn.
- Mã lỗi: NOT_FOUND, FORBIDDEN, INVALID_REGISTRATION_STATUS, REASON_REQUIRED, SESSION_NOT_ACCEPTING_REVIEWS, CHECKS_NOT_PASSED (kèm details), INVALID_SUPPLEMENT_DEADLINE, SUPPLEMENT_EXPIRED, NOTHING_TO_UPDATE; VALIDATION_ERROR/BUSINESS_RULE_VIOLATION qua DTO và lưu tệp. Không khác đặc tả.
- Ruff check/format sạch. Không DB: 38 passed, 121 skipped. Toàn bộ test hiện có trên dgtt_test_codex: 159 passed; lỗi payload test TASK-003 đã được Claude sửa. Test riêng TASK-002 của Claude chưa có tại lúc chạy.
- Đã chạy kịch bản httpx riêng trên dgtt_test_codex: đủ 3 checks; mới nhất FAILED chặn duyệt rồi PASSED cho duyệt; thiếu reason/hạn bị chặn; 10 lượt duyệt đồng thời nhận đúng NTG-01..NTG-10; kiểm tra audit, lọc/phân trang, staff xem căn cứ và chủ hồ sơ không thấy căn cứ, người khác bị 403; nộp bổ sung tăng lần nộp và tải lại tệp cũ thành công.
- Thử nhanh trên dev dgtt: staff đăng nhập rồi GET `/api/v1/registrations` trả 200, total=2; chi tiết không token trả 401. Các bước ghi đã thử trên DB riêng để giữ dữ liệu dev ổn định.

## Kết quả kiểm thử (Claude)

**Thời điểm:** 2026-11-25 22:08 (giờ Việt Nam) · **Kết luận:** DONE

**Lệnh đã chạy:**

| Lệnh | Kết quả |
|---|---|
| `ruff check .` · `ruff format --check .` | Sạch (102 file) |
| `pytest` (không DB) | 43 đạt, 192 bỏ qua (cần DB) |
| `TEST_DATABASE_URL=…/dgtt_test pytest` (toàn bộ) | **235/235 đạt**, không hồi quy |
| Riêng TASK-002 (`test_registration_review_api.py` + `test_registration_concurrency.py`) | 77/77 đạt |

**Tiêu chí chấp nhận:**

| AC | Kết quả | Test |
|---|---|---|
| AC-1 | Đạt | `test_staff_list_filters_and_pagination`, `test_staff_list_forbidden_for_other_roles` |
| AC-2 | Đạt | `test_approve_after_three_checks_assigns_alias`, `test_approve_in_upcoming_session` |
| AC-3 | Đạt | `test_approve_checks_not_passed` (thiếu bước / thiếu DEPOSIT / FAILED sau PASSED), `test_approve_after_failed_then_passed` |
| AC-4 | Đạt | `test_check_failed_requires_reason` |
| AC-5 | Đạt | `test_request_supplement_success`, `test_request_supplement_requires_reason`, `test_request_supplement_invalid_deadline` (thiếu / quá khứ / bằng hiện tại / bằng và sau `start_time`) |
| AC-6 | Đạt | `test_reject_success`, `test_reject_requires_reason` |
| AC-7 | Đạt | `test_decision_requires_pending`, `test_check_requires_pending` |
| AC-8 | Đạt | `test_resubmit_before_deadline`, `test_resubmit_text_only` |
| AC-9 | Đạt | `test_resubmit_after_deadline`, `test_resubmit_requires_needs_supplement`, `test_resubmit_by_other_user_forbidden` |
| AC-10 | Đạt | `test_reject_expired_supplement` |
| AC-11 | Đạt | kiểm trong các test thành công ở trên (đúng 1 dòng `registration_reviews` + 1 dòng `activity_logs`, đúng `action`, `field_name`/`old_value`/`new_value`/`reason`) |
| AC-12 | Đạt | `test_registration_detail_permissions` |
| AC-13 | Đạt | `test_concurrent_approvals_unique_aliases` (10 hồ sơ → NTG-01…NTG-10) |
| Bổ sung | Đạt | `test_decision_session_not_accepting_reviews`, `test_*_validation_error`, `test_*_requires_staff`, `test_*_unknown_registration`, `test_resubmit_nothing_to_update`, `test_resubmit_invalid_input`, `test_review_endpoints_without_token_return_401` |

**Kiểm tra thêm bằng request thủ công (test tạm, đã xoá):**

- 4 request `APPROVE` đồng thời trên **cùng** một hồ sơ → đúng 1 lần 200 (NTG-01), 3 lần 422 `INVALID_REGISTRATION_STATUS`.
- Nộp lại có 1 tệp hợp lệ + 1 tệp `.exe` → 422; tệp hợp lệ vừa lưu bị dọn, tệp của lần nộp 1 còn nguyên trên đĩa và trong DB.

**Lỗi trong test của Claude đã sửa trong lượt viết test:** ca `at-start-time` gửi hạn đã cắt micro giây nên thực tế sớm hơn
`start_time` → sửa test gửi đúng `start_time`. Không phải lỗi code.

**Review code (AGENTS.md Mục 4):**

- Chia lớp đúng; vai trò kiểm ở router (`StaffUser`, `BidderUser`, chủ hồ sơ/STAFF cho chi tiết), phạm vi dữ liệu qua `permissions.py`.
- `_load_locked` khóa **phiên trước, hồ sơ sau** (thống nhất thứ tự với nộp hồ sơ, tránh deadlock) và đọc lại hồ sơ sau khi khóa.
  Cấp `bidder_alias` dưới khóa phiên → Mục 4.10 và Quy tắc 3 đạt.
- Mỗi thao tác: 1 dòng `registration_reviews` (quyết định có `result = NULL`) + `log_activity` trước `commit`, cùng transaction.
- `APPROVE` dùng `latest_check_results` + `all_checks_passed`; `CHECKS_NOT_PASSED` trả `details` là kết quả từng bước.
- Nộp lại: tăng `submission_count`, tệp mới mang số lần nộp mới, giữ tệp cũ và `supplement_deadline`; rollback + dọn tệp mới khi lỗi.
- Chủ hồ sơ không thấy `reviewed_by`/`evidence`; STAFF thấy đủ. Dùng `utcnow()`, enum, lớp lỗi chuẩn.

**Ghi chú nhỏ (không chặn DONE):**

- `resubmit` gán `subdir` **trước** khi chụp danh sách tệp có sẵn (ngược thứ tự với `submit_registration`). Nếu `iterdir()`
  lỗi đúng ở bước đó thì bước dọn có thể coi tệp cũ là tệp mới. Rất khó xảy ra; nên đổi thứ tự khi có dịp sửa module.
- `ensure_owner_or_staff` trong `resubmit` cho STAFF qua, nhưng router đã giới hạn `BIDDER` nên không có lỗ hổng.
- `checks` không kiểm tra trạng thái phiên (đặc tả chỉ yêu cầu với `decision`), nên vẫn ghi được bước đối chiếu khi phiên đã diễn ra.
- Hạ tầng test (phần của Claude): thư mục `storage/` không được dọn giữa các lần chạy test, trong khi DB test tạo lại từ đầu
  nên `registration_id` lặp lại → tệp cũ của lần chạy trước nằm chung thư mục. Không ảnh hưởng kết quả; Claude sẽ cân nhắc
  cho test dùng thư mục lưu trữ tạm riêng.

## Quyết định của người dùng

_(Trống.)_

## Lịch sử

- 2026-11-25 20:40 | Claude | TODO | Tạo task

- 2026-11-25 21:37 | Codex | IN_PROGRESS | TASK-001 đã DONE; bắt đầu đối chiếu, quyết định và nộp lại hồ sơ.

- 2026-11-25 21:40 | Codex | REVIEW | Bàn giao TASK-002; 159 test hiện có đạt, kiểm tra riêng luồng xét duyệt và đồng thời 10 hồ sơ đạt.

- 2026-11-25 22:01 | Claude | TESTING | Nhận kiểm thử TASK-002.

- 2026-11-25 22:08 | Claude | DONE | 235/235 test đạt trên dgtt_test; mọi AC đạt.
