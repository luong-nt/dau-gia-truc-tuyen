# TASK-010: Thống kê hoạt động và tra cứu nhật ký

- **Trạng thái:** REVIEW
- **FR/NFR liên quan:** FR-24, FR-26, NFR-05
- **Module:** `app/modules/reports`
- **Phụ thuộc:** TASK-013 (kiểu `Money` cho tổng giá trúng)
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

Quản trị viên và Nhân viên xem số liệu tổng hợp trong một khoảng thời gian: tài sản và hồ sơ theo trạng thái, phiên theo trạng
thái và theo kết quả (tách **phiên chờ xác nhận** với **phiên đã có kết quả chính thức**). Quản trị viên tra cứu nhật ký hoạt động
(chỉ đọc). Module `reports` **chỉ đọc** dữ liệu.

## Phạm vi file được sửa (Codex)

- `app/modules/reports/router.py`
- `app/modules/reports/schemas.py`
- `app/modules/reports/service.py`
- `app/modules/reports/repository.py` (tạo mới)

Chỉ **dùng**: `app/core/money.py`, `app/core/pagination.py`.

## Đặc tả API

### Khoảng thời gian (dùng chung cho TASK-010, TASK-011)

- Query `from`, `to`: datetime ISO 8601 **không múi giờ, hiểu là UTC** (cùng quy ước `utcnow()`), đều tuỳ chọn.
- Lọc nửa mở: `from ≤ t < to`. Thiếu cận nào thì không giới hạn phía đó.
- `from` và `to` cùng có mà `from ≥ to` → 422 `INVALID_DATE_RANGE`. Sai định dạng → 422 `VALIDATION_ERROR`.

### 1. `GET /api/v1/reports/summary`

- **Vai trò:** ADMIN, STAFF. AUCTIONEER, BIDDER → 403 `FORBIDDEN`. Không token → 401.
- **Query:** `from`, `to`.
- **Response 200** `SummaryOut`:

| Trường | Ý nghĩa | Mốc thời gian dùng để lọc |
|---|---|---|
| `date_from`, `date_to` | tham số đã nhận (`null` nếu không gửi) | |
| `generated_at` | `utcnow()` | |
| `assets_by_status` | object có **đủ 4 khoá** `UPCOMING`, `IN_AUCTION`, `ENDED`, `SUSPENDED_CANCELLED` → số tài sản | `assets.created_at` |
| `registrations_by_status` | **đủ 4 khoá** `PENDING`, `NEEDS_SUPPLEMENT`, `APPROVED`, `REJECTED` → số hồ sơ | `registrations.submitted_at` |
| `sessions_by_status` | **đủ 7 khoá** của `SessionStatus` → số phiên | `auction_sessions.start_time` |
| `session_results` | `{awaiting_confirmation, confirmed_with_winner, confirmed_failed}` | `start_time`, chỉ phiên `ENDED` |
| `total_confirmed_amount` | `Money`: tổng giá trúng của **bản `CONFIRMED`** thuộc các phiên `ENDED` trong khoảng; không có thì `"0"` | |

  Quy tắc `session_results` cho mỗi phiên `ENDED` trong khoảng:
  - có bản `CONFIRMED` với `winning_bid_id` khác `null` → `confirmed_with_winner`;
  - có bản `CONFIRMED` với `winning_bid_id` `null` → `confirmed_failed`;
  - không có bản `CONFIRMED` (chỉ có `DRAFT`, hoặc chưa có kết quả) → `awaiting_confirmation`.
  Bản `DRAFT`/`SUPERSEDED` **không** được cộng vào `total_confirmed_amount` (FR-25).

### 2. `GET /api/v1/activity-logs`

- **Vai trò:** chỉ ADMIN. STAFF, AUCTIONEER, BIDDER → 403. Không token → 401.
- **Query:** `user_id`, `action` (khớp chính xác), `entity_type` (chính xác), `entity_id`, `from`, `to` (lọc `created_at`),
  `page`, `size` (`Pagination`).
- **Response 200:** `Page[ActivityLogOut]` (schema đã có), sắp `created_at` giảm dần rồi `log_id` giảm dần.
- **Lỗi:** 422 `INVALID_DATE_RANGE`, 422 `VALIDATION_ERROR` (tham số sai kiểu).
- **Chỉ đọc:** không có endpoint sửa/xoá nhật ký (AGENTS.md Mục 4.7).

## Quy tắc nghiệp vụ

1. Đếm bằng truy vấn tổng hợp (`GROUP BY`) trong repository, không tải toàn bộ dòng lên Python.
2. Không ghi DB, không ghi nhật ký khi xem thống kê/nhật ký.

## Tiêu chí chấp nhận

- **AC-1:** `summary`: không token → 401; AUCTIONEER, BIDDER → 403; ADMIN, STAFF → 200, có đủ khoá kể cả giá trị 0.
- **AC-2:** Lọc theo khoảng: số tài sản/hồ sơ/phiên theo trạng thái đúng với dữ liệu trong khoảng, không đếm dữ liệu ngoài khoảng
  (cận `to` loại trừ).
- **AC-3:** `session_results` tách đúng chờ xác nhận / đã có kết quả có người trúng / không thành; phiên có bản `CONFIRMED` kèm bản
  điều chỉnh `DRAFT` tính là đã có kết quả.
- **AC-4:** `total_confirmed_amount` chỉ cộng bản `CONFIRMED` (bỏ `DRAFT`, `SUPERSEDED`), dạng chuỗi chữ số.
- **AC-5:** Không gửi `from`/`to` → đếm toàn bộ (tạo thêm 1 tài sản `UPCOMING` thì `UPCOMING` tăng đúng 1).
- **AC-6:** `from ≥ to` → 422 `INVALID_DATE_RANGE` (cả hai endpoint); `from` sai định dạng → 422 `VALIDATION_ERROR`.
- **AC-7:** `activity-logs`: không token → 401; STAFF, AUCTIONEER, BIDDER → 403; ADMIN lọc đúng theo `user_id`, `action`,
  `entity_type`, `entity_id`, khoảng `created_at`; sắp mới nhất trước; phân trang có `total`.
- **AC-8:** Không có endpoint sửa/xoá nhật ký: `PUT`/`PATCH`/`DELETE /api/v1/activity-logs/{id}` không trả 2xx và dòng nhật ký còn nguyên.

## Kế hoạch kiểm thử (Claude)

| AC | Test | File |
|---|---|---|
| AC-1 | `test_summary_auth`, `test_summary_without_token_401` | `tests/api/test_reports_api.py` |
| AC-2, AC-3, AC-4 | `test_summary_in_window` | `tests/api/test_reports_api.py` |
| AC-5 | `test_summary_all_time_delta` | `tests/api/test_reports_api.py` |
| AC-6 | `test_invalid_date_range` | `tests/api/test_reports_api.py` |
| AC-7 | `test_activity_logs_auth`, `test_activity_logs_filters` | `tests/api/test_reports_api.py` |
| AC-8 | `test_activity_logs_read_only` | `tests/api/test_reports_api.py` |

## Ghi chú triển khai (Codex)

**KẾT LUẬN HIỆN TẠI CỦA CODEX: CHẤP THUẬN HOÀN TẤT, không còn chờ Codex.** 9/9 ca thống kê/nhật ký đạt,
lượt cuối full-system-10.xml không hồi quy. Claude cập nhật DONE theo phản hồi kiểm thử độc lập đã ghi bên dưới.

**Người triển khai: Claude** (theo chỉ thị người dùng 2026-11-26 trong `CLAUDE.md`; Codex kiểm thử độc lập).

- **File đã sửa:** `app/modules/reports/router.py`, `schemas.py` (`SummaryOut`, `SessionResultsSummary`), `service.py`
  (`normalize_range`, `get_summary`, `search_activity_logs`), `repository.py` (mới: đếm `GROUP BY`, tổng hợp kết quả bằng
  `COUNT(*) FILTER` + `SUM`, tìm nhật ký).
- **Endpoint:** `GET /reports/summary` (ADMIN, STAFF), `GET /activity-logs` (chỉ ADMIN; không có API sửa/xoá).
- **Mã lỗi:** `INVALID_DATE_RANGE` (422), `VALIDATION_ERROR` (422), 401/403.
- **Ghi chú:** tham số `from`/`to` (alias) hiểu là UTC; có múi giờ thì đổi về UTC không múi giờ. Khoảng nửa mở `[from, to)`.
  Bản `CONFIRMED` lấy qua outer join có điều kiện `status = CONFIRMED`; DRAFT/SUPERSEDED không cộng vào tổng.
  `total_confirmed_amount` kiểu `Money`. Không ghi DB, không ghi nhật ký khi xem.
- **Khác đặc tả:** không.
- **Tự kiểm tra (2026-11-26 23:20):** ruff sạch. `tests/api/test_reports_api.py` 9/9.
  `dgtt_test` toàn bộ (gồm TASK-010 và TASK-011): **367 passed, 2 skipped, 1 failed** — chỉ TC-RES-003 (PDF 503 thiếu Pango,
  lỗi môi trường). Không hồi quy.

### Phản hồi kiểm thử độc lập mã hiện có — Codex, 2026-11-26 21:10

- `logs/test-results/full-system-09.xml` trên dgtt_test_codex: **367 passed, 1 failed, 2 skipped**; **9/9 ca thống kê/
  nhật ký đạt**, không ca từng đạt bị hồi quy. Ruff check/format sạch.
- Review: truy vấn GROUP BY/aggregate trong repository, khoảng nửa mở [from,to), đủ khóa trạng thái kể cả 0, tổng chỉ tính
  CONFIRMED của phiên ENDED; nhật ký chỉ ADMIN, chỉ đọc, phân trang và thứ tự ổn định.
- **Mã TASK-010 hiện tại đạt kiểm thử độc lập**, có thể hoàn tất sau khi Claude ghi xong bàn giao nếu không thay đổi mã tiếp.
  Lỗi duy nhất toàn hệ thống là TC-RES-003 thiếu Pango, không thuộc TASK-010. TASK-012 mới sẽ được kiểm riêng khi bàn giao.

## Kết quả kiểm thử (Claude)

_(Claude điền khi kiểm thử.)_

## Quyết định của người dùng

_(Không có.)_

## Lịch sử

- 2026-11-26 10:45 | Claude | TODO | Tạo task
- 2026-11-26 22:40 | Claude | IN_PROGRESS | Claude triển khai theo chỉ thị trong CLAUDE.md
- 2026-11-26 23:20 | Claude | REVIEW | Bàn giao, chờ Codex kiểm thử độc lập
