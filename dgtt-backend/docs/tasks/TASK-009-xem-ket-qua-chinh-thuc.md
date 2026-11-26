# TASK-009: Người tham gia xem kết quả đã xác nhận

- **Trạng thái:** REVIEW
- **FR/NFR liên quan:** FR-23 (các bên xem theo quyền, phân biệt dự thảo/đã xác nhận), NFR-05, AGENTS.md Mục 5.11
- **Module:** `app/modules/results`
- **Phụ thuộc:** TASK-006 (chung file `results/router.py`, `service.py`, `permissions.py`), TASK-013
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

Người tham gia được duyệt của một phiên cần xem **kết quả chính thức** (bản `CONFIRMED`) của phiên đó: người trúng là ai
(mã ẩn danh), giá trúng, có phải mình trúng không. Bản dự thảo **không** được hiển thị cho người tham gia. Nội bộ (Nhân viên,
Quản trị viên, Đấu giá viên phụ trách) dùng cùng endpoint để xem nhanh kết quả chính thức.

## Phạm vi file được sửa (Codex)

- `app/modules/results/router.py`
- `app/modules/results/schemas.py`
- `app/modules/results/service.py`
- `app/modules/results/repository.py`
- `app/modules/results/permissions.py`

## Đặc tả API

### `GET /api/v1/sessions/{session_id}/results/official`

Khai báo route này **trước** các route có `{result_id}` nếu cần để tránh trùng đường dẫn.

- **Vai trò và phạm vi** (giống TASK-006): STAFF, ADMIN, AUCTIONEER được phân công, BIDDER có hồ sơ `APPROVED` trong phiên.
- **Response 200** `OfficialResultOut`:

| Trường | Kiểu | Giá trị |
|---|---|---|
| `result_id` | int | bản `CONFIRMED` hiện hành |
| `session_id` | int | |
| `session_code` | string | `PDG-{session_id}` |
| `version_no` | int | |
| `confirmed_at` | datetime | |
| `is_failed` | bool | `true` khi `winning_bid_id` là `null` (đấu giá không thành) |
| `winning_bidder_alias` | string \| null | `null` khi không thành |
| `winning_amount` | `Money` \| null | chuỗi chữ số (TASK-013); `null` khi không thành |
| `exception_note` | string \| null | |
| `my_alias` | string \| null | BIDDER: `bidder_alias` của mình trong phiên; vai trò khác: `null` |
| `is_mine` | bool | BIDDER: `true` nếu lượt giá trúng thuộc hồ sơ của mình; vai trò khác: `false` |

  **Không** có: `winning_bid_id`, `confirmed_by`, `bidder_id`, họ tên, số giấy tờ, `adjustment_reason`.

- **Lỗi** (kiểm tra theo thứ tự):

| Tình huống | HTTP | `code` |
|---|---|---|
| Chưa đăng nhập | 401 | `UNAUTHORIZED` |
| Phiên không tồn tại | 404 | `NOT_FOUND` |
| Không thuộc nhóm được xem (AUCTIONEER khác, BIDDER không có hồ sơ `APPROVED` trong phiên) | 403 | `FORBIDDEN` |
| Phiên chưa có bản `CONFIRMED` (chưa có kết quả, hoặc mới có bản `DRAFT`) | 404 | `NO_CONFIRMED_RESULT` |

## Quy tắc nghiệp vụ

1. Trả đúng **bản `CONFIRMED` duy nhất** của phiên. Đang có bản điều chỉnh `DRAFT` chờ xác nhận thì vẫn trả bản `CONFIRMED` cũ.
   Bản `SUPERSEDED` không bao giờ được trả.
2. Chỉ đọc: không ghi DB, không ghi nhật ký.
3. Không trả dữ liệu định danh (AGENTS.md Mục 5.11).

## Tiêu chí chấp nhận

- **AC-1:** Không token → 401.
- **AC-2:** BIDDER trúng (NTG-02) xem → 200, đúng các trường, `is_mine = true`, `my_alias = "NTG-02"`,
  `winning_amount = "105000000"`, `session_code = "PDG-{sid}"`; response không có trường cấm.
- **AC-3:** BIDDER không trúng (NTG-01) → `is_mine = false`, `my_alias = "NTG-01"`.
- **AC-4:** STAFF, ADMIN, đấu giá viên phụ trách → 200, `my_alias = null`, `is_mine = false`.
- **AC-5:** Đấu giá viên khác, BIDDER không có hồ sơ, BIDDER hồ sơ `PENDING`/`REJECTED` → 403 `FORBIDDEN`.
- **AC-6:** Phiên chỉ có bản `DRAFT`, hoặc chưa có kết quả → 404 `NO_CONFIRMED_RESULT`; phiên không tồn tại → 404 `NOT_FOUND`.
- **AC-7:** Có v1 `SUPERSEDED`, v2 `CONFIRMED`, v3 `DRAFT` → trả v2.
- **AC-8:** Bản `CONFIRMED` không thành → `is_failed = true`, `winning_bidder_alias`, `winning_amount` là `null`, có `exception_note`.

## Kế hoạch kiểm thử (Claude)

| AC | Test | File |
|---|---|---|
| AC-1 | `test_official_without_token_401` | `tests/api/test_official_result_api.py` |
| AC-2, AC-3 | `test_official_bidder_view` | `tests/api/test_official_result_api.py` |
| AC-4 | `test_official_internal_view` | `tests/api/test_official_result_api.py` |
| AC-5 | `test_official_forbidden` | `tests/api/test_official_result_api.py` |
| AC-6 | `test_official_not_confirmed`, `test_official_session_not_found` | `tests/api/test_official_result_api.py` |
| AC-7 | `test_official_picks_confirmed_version` | `tests/api/test_official_result_api.py` |
| AC-8 | `test_official_failed_auction` | `tests/api/test_official_result_api.py` |

## Ghi chú triển khai (Codex)

**KẾT LUẬN HIỆN TẠI CỦA CODEX: CHẤP THUẬN HOÀN TẤT, không còn chờ Codex.** 8/8 ca kết quả chính thức đạt,
lượt cuối full-system-10.xml không hồi quy. Claude cập nhật DONE theo phản hồi kiểm thử độc lập đã ghi bên dưới.

**Người triển khai: Claude** (theo chỉ thị người dùng 2026-11-26 trong `CLAUDE.md`; Codex kiểm thử độc lập).

- **File đã sửa:** `app/modules/results/router.py` (route `GET /official` khai báo trước các route `{result_id}`),
  `schemas.py` (`OfficialResultOut`, `winning_amount` kiểu `Money`), `service.py` (`get_official_result`),
  `repository.py` (`get_confirmed_detail`), `permissions.py` (`ensure_can_view_official`, `is_approved_participant`
  đã thêm ở TASK-006).
- **Mã lỗi:** `NOT_FOUND` (phiên), `FORBIDDEN` (403), `NO_CONFIRMED_RESULT` (404).
- **Ghi chú:** chỉ đọc, không log. `is_mine` so `registration_id` của lượt giá trúng với hồ sơ APPROVED của người gọi;
  vai trò nội bộ luôn `my_alias = null`, `is_mine = false`. Không trả `winning_bid_id`, `confirmed_by`, `adjustment_reason`.
- **Khác đặc tả:** không.
- **Tự kiểm tra (2026-11-26 22:50):** ruff sạch. `tests/api/test_official_result_api.py` 8/8; minutes + results vẫn đạt.
  `dgtt_test` toàn bộ: 350 passed, 2 skipped, 18 failed (reports 8, report_export 9 — task chưa làm; TC-RES-003 — thiếu
  Pango). Không hồi quy (342 → 350).

### Kiểm thử độc lập — Codex, 2026-11-26 21:10

- `logs/test-results/full-system-09.xml` trên dgtt_test_codex: **367 passed, 1 failed, 2 skipped**; **8/8 ca kết quả
  chính thức đạt**, không ca từng đạt bị hồi quy. Ruff check/format sạch.
- Review: chỉ chọn CONFIRMED hiện hành, giữ bản chính thức cũ khi bản điều chỉnh còn DRAFT; quyền kiểm tra trước đọc kết quả;
  DTO không lộ định danh người trúng, is_mine so sánh registration_id, không ghi DB/audit cho thao tác xem.
- **TASK-009 đạt kiểm thử độc lập, đủ điều kiện hoàn tất.** Lỗi duy nhất còn lại là TC-RES-003 thiếu Pango cho PDF thật,
  không phải lỗi endpoint kết quả chính thức. Thay đổi TASK-012 trong lúc chạy sẽ được kiểm bằng lượt tiếp theo.

## Kết quả kiểm thử (Claude)

_(Claude điền khi kiểm thử.)_

## Quyết định của người dùng

_(Không có.)_

## Lịch sử

- 2026-11-26 09:35 | Claude | TODO | Tạo task
- 2026-11-26 22:25 | Claude | IN_PROGRESS | Claude triển khai (mã TASK-006 đã có, đang REVIEW)
- 2026-11-26 22:50 | Claude | REVIEW | Bàn giao, chờ Codex kiểm thử độc lập
