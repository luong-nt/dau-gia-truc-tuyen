# TASK-005: Xác nhận, điều chỉnh kết quả đấu giá và đồng bộ trạng thái tài sản

- **Trạng thái:** DONE
- **FR/NFR liên quan:** FR-23 (xác nhận, điều chỉnh), FR-22 (xem kết quả dự kiến), NFR-05, NFR-06, FR-26
- **Module:** `app/modules/results`
- **Phụ thuộc:** Không (không chung file với TASK-004, làm song song được)
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

Khi phiên kết thúc, hệ thống đã tự tạo kết quả bản 1 ở trạng thái `DRAFT` (`results.service.create_draft_result`).
Task này cho đấu giá viên phụ trách: xem các phiên bản kết quả kèm giá trúng và mã người trúng, **xác nhận** bản dự thảo
(kèm ghi nhận xử lý ngoại lệ), và **điều chỉnh** kết quả đã xác nhận bằng một phiên bản mới có lý do. Khi xác nhận, bản
`CONFIRMED` cũ (nếu có) chuyển `SUPERSEDED` và trạng thái tài sản được đồng bộ theo AGENTS.md Mục 5.7.

Ngoài phạm vi: xuất biên bản PDF (TASK-006), người tham gia xem kết quả (TASK-009).

## Phạm vi file được sửa (Codex)

- `app/modules/results/router.py`
- `app/modules/results/schemas.py`
- `app/modules/results/service.py`
- `app/modules/results/repository.py`
- `app/modules/results/permissions.py` (tạo mới nếu cần)

Chỉ **dùng** (không sửa): `app/modules/sessions/repository.py` (`get_session`, `get_session_for_update`, `get_asset`),
`app/modules/sessions/permissions.py`, `app/modules/bidding/repository.py`.
Giữ nguyên chữ ký và hành vi của `create_draft_result` (module `sessions` đang gọi).

## Đặc tả API

Router đã gắn prefix `/api/v1/sessions/{session_id}/results`.

### `ResultOut` (dùng cho cả 3 endpoint)

Các trường hiện có của `ResultOut` **cộng thêm**:

| Trường | Kiểu | Giá trị |
|---|---|---|
| `winning_amount` | Decimal \| null | `bids.amount` của `winning_bid_id`; `null` khi đấu giá không thành |
| `winning_bidder_alias` | string \| null | `registrations.bidder_alias` của lượt giá trúng; `null` khi không thành |

Không trả `bidder_id`, họ tên hay số giấy tờ của người trúng.

### 1. `GET /api/v1/sessions/{session_id}/results`  (đã có, bổ sung trường)

- **Vai trò:** giữ như hiện tại: STAFF, ADMIN, AUCTIONEER được phân công (`can_view_internal`)
- **Response 200:** `list[ResultOut]`, sắp `version_no` tăng dần
- **Lỗi:** 401; 403 `FORBIDDEN`; 404 `NOT_FOUND` (phiên không tồn tại)

### 2. `POST /api/v1/sessions/{session_id}/results/{result_id}/confirm`

- **Vai trò:** AUCTIONEER **được phân công** phiên
- **Request JSON:** `{"exception_note": "…"}`, `exception_note` tuỳ chọn, ≤ 2000 ký tự. Có gửi (kể cả chuỗi rỗng) thì
  ghi đè `exception_note` của bản đang xác nhận; không gửi thì giữ nguyên. Body rỗng `{}` hợp lệ.
- **Response 200:** `ResultOut` của bản vừa xác nhận
- **Lỗi** (kiểm tra theo đúng thứ tự):

| Tình huống | HTTP | `code` |
|---|---|---|
| Chưa đăng nhập | 401 | `UNAUTHORIZED` |
| Không phải AUCTIONEER (STAFF, ADMIN, BIDDER) | 403 | `FORBIDDEN` |
| Phiên không tồn tại | 404 | `NOT_FOUND` |
| AUCTIONEER không được phân công phiên này | 403 | `FORBIDDEN` |
| `result_id` không tồn tại hoặc không thuộc phiên `session_id` | 404 | `NOT_FOUND` |
| Bản kết quả không ở `DRAFT` | 422 | `RESULT_NOT_DRAFT` |
| `exception_note` quá 2000 ký tự | 422 | `VALIDATION_ERROR` |

### 3. `POST /api/v1/sessions/{session_id}/results`  (điều chỉnh)

- **Vai trò:** AUCTIONEER **được phân công** phiên
- **Request JSON** (`AdjustResultRequest`, sửa lại cho đúng bảng này):

| Trường | Bắt buộc | Ràng buộc |
|---|---|---|
| `winning_bid_id` | Có (được `null` = đấu giá không thành) | `bid_id` của một lượt `ACCEPTED` thuộc phiên này |
| `exception_note` | Không | ≤ 2000 ký tự |
| `adjustment_reason` | Có | bỏ khoảng trắng đầu/cuối, 1–500 ký tự |

- **Response 201:** `ResultOut` của phiên bản mới (`DRAFT`)
- **Lỗi** (kiểm tra theo đúng thứ tự):

| Tình huống | HTTP | `code` |
|---|---|---|
| Chưa đăng nhập | 401 | `UNAUTHORIZED` |
| Không phải AUCTIONEER | 403 | `FORBIDDEN` |
| Thiếu `winning_bid_id` (không gửi khoá), thiếu/rỗng/toàn khoảng trắng/quá dài `adjustment_reason`, `exception_note` quá dài | 422 | `VALIDATION_ERROR` |
| Phiên không tồn tại | 404 | `NOT_FOUND` |
| AUCTIONEER không được phân công | 403 | `FORBIDDEN` |
| Phiên không ở `ENDED` | 422 | `SESSION_NOT_ENDED` |
| Phiên bản mới nhất đang `DRAFT` (chưa xác nhận) | 409 | `DRAFT_RESULT_PENDING` |
| Phiên chưa có bản `CONFIRMED` nào (không có phiên bản nào) | 409 | `NO_CONFIRMED_RESULT` |
| `winning_bid_id` không tồn tại, là lượt `REJECTED`, hoặc thuộc phiên khác | 422 | `INVALID_WINNING_BID` |

## Quy tắc nghiệp vụ

1. **Khóa:** confirm và điều chỉnh đều khóa dòng phiên bằng `sessions.repository.get_session_for_update` trước khi đọc
   các phiên bản kết quả (AGENTS.md Mục 4.10), để hai thao tác đồng thời không tạo trùng `version_no` hay hai bản `CONFIRMED`.
2. **Một bản dự thảo tại một thời điểm.** Theo AGENTS.md Mục 5.8, điều chỉnh được thực hiện trên kết quả **đã xác nhận**:
   chỉ tạo phiên bản mới khi phiên bản mới nhất đang `CONFIRMED`. Muốn ghi nhận xử lý ngoại lệ trước khi xác nhận thì gửi
   `exception_note` kèm lệnh confirm.
3. **Xác nhận** bản `DRAFT`:
   - Nếu phiên đã có bản `CONFIRMED`: đổi bản đó sang `SUPERSEDED` và `flush` **trước**, rồi mới đặt bản mới `CONFIRMED`
     (tránh vi phạm unique index `uq_results_one_confirmed`).
   - Đặt `status = CONFIRMED`, `confirmed_by` = đấu giá viên, `confirmed_at = utcnow()`.
4. **Đồng bộ tài sản khi xác nhận** (AGENTS.md Mục 5.7), áp dụng ở **mọi** lần xác nhận (kể cả xác nhận bản điều chỉnh):
   - `winning_bid_id` khác `null` → `assets.status = ENDED`.
   - `winning_bid_id` là `null` (đấu giá không thành) → `assets.status = UPCOMING`.
5. **Điều chỉnh:** tạo dòng mới `version_no` = lớn nhất + 1, `status = DRAFT`, `winning_bid_id`, `exception_note`,
   `adjustment_reason` (đã bỏ khoảng trắng), `confirmed_by`/`confirmed_at`/`minutes_url` = `null`.
   **Không** sửa bản `CONFIRMED` hiện tại (nó chỉ thành `SUPERSEDED` khi bản mới được xác nhận). Không đổi trạng thái tài sản.
   Được phép giữ nguyên `winning_bid_id` (chỉ điều chỉnh ghi chú ngoại lệ).
6. **Nhật ký (FR-26)**, `log_activity` trước `commit`, cùng transaction, `user_id` = đấu giá viên:

| Thao tác | `action` | `entity_type` | `entity_id` | `field_name` | `old_value` → `new_value` | `reason` |
|---|---|---|---|---|---|---|
| Xác nhận | `CONFIRM_RESULT` | `auction_result` | bản được xác nhận | `status` | `DRAFT` → `CONFIRMED` | — |
| Bản cũ bị thay | `SUPERSEDE_RESULT` | `auction_result` | bản CONFIRMED cũ | `status` | `CONFIRMED` → `SUPERSEDED` | — |
| Đổi trạng thái tài sản (chỉ khi giá trị thật sự đổi) | `UPDATE_ASSET_STATUS` | `asset` | `asset_id` | `status` | cũ → mới | — |
| Điều chỉnh | `ADJUST_RESULT` | `auction_result` | bản **mới** | `winning_bid_id` | `winning_bid_id` của bản CONFIRMED hiện tại → của bản mới (`null` ghi là `None`/rỗng đều được) | `adjustment_reason` |

7. Dùng `utcnow()`, enum `ResultStatus`, `AssetStatus`, `BidResult`; lỗi qua `app/core/exceptions.py`.
8. Không broadcast realtime trong task này.

## Tiêu chí chấp nhận

- **AC-1:** `GET` trả các phiên bản theo `version_no`, có `winning_amount`, `winning_bidder_alias` đúng; bản không thành có
  2 trường này `null`; không có trường định danh người trúng. BIDDER, AUCTIONEER khác → 403; không token → 401; phiên không có → 404.
- **AC-2:** Đấu giá viên phụ trách xác nhận bản 1 `DRAFT` có người trúng → 200, `CONFIRMED`, `confirmed_by`, `confirmed_at`;
  tài sản `IN_AUCTION` → `ENDED`; log `CONFIRM_RESULT` + `UPDATE_ASSET_STATUS`.
- **AC-3:** Xác nhận bản `DRAFT` không có người trúng → tài sản `UPCOMING`.
- **AC-4:** Confirm có `exception_note` → lưu vào bản kết quả; không gửi → giữ ghi chú cũ.
- **AC-5:** Xác nhận bản đã `CONFIRMED` hoặc `SUPERSEDED` → 422 `RESULT_NOT_DRAFT`, dữ liệu không đổi.
- **AC-6:** Điều chỉnh khi bản mới nhất `CONFIRMED` → 201, bản mới `version_no + 1`, `DRAFT`, có `adjustment_reason`;
  bản CONFIRMED cũ giữ nguyên `CONFIRMED`; tài sản không đổi; log `ADJUST_RESULT` có `reason`.
- **AC-7:** Xác nhận bản điều chỉnh → bản cũ `SUPERSEDED`, bản mới `CONFIRMED`, chỉ một bản `CONFIRMED`; log `SUPERSEDE_RESULT`;
  tài sản đồng bộ theo bản mới (ví dụ có người trúng → không thành: `ENDED` → `UPCOMING`).
- **AC-8:** Điều chỉnh khi bản mới nhất còn `DRAFT` → 409 `DRAFT_RESULT_PENDING`; phiên chưa `ENDED` → 422 `SESSION_NOT_ENDED`;
  phiên `ENDED` chưa có phiên bản nào → 409 `NO_CONFIRMED_RESULT`. Không tạo dòng mới.
- **AC-9:** `winning_bid_id` là lượt `REJECTED`, thuộc phiên khác, hoặc không tồn tại → 422 `INVALID_WINNING_BID`.
- **AC-10:** Thiếu/rỗng/toàn khoảng trắng `adjustment_reason`, thiếu khoá `winning_bid_id` → 422 `VALIDATION_ERROR`.
- **AC-11:** STAFF, ADMIN, BIDDER, AUCTIONEER khác gọi confirm/điều chỉnh → 403; không token → 401;
  `result_id` thuộc phiên khác → 404.
- **AC-12:** Hai lệnh confirm đồng thời cùng một bản → đúng một 200, một 422 `RESULT_NOT_DRAFT`; hai lệnh điều chỉnh đồng
  thời → đúng một 201, một 409 `DRAFT_RESULT_PENDING`; không có lỗi 500, không trùng `version_no`.

## Kế hoạch kiểm thử (Claude)

| AC | File |
|---|---|
| AC-1 … AC-11 | `tests/api/test_results_api.py` |
| AC-12 | `tests/concurrency/test_result_concurrency.py` |

Dữ liệu: Claude thêm vào `tests/factories.py` hàm tạo lượt giá (`create_bid`), kết quả (`create_result`) và kịch bản phiên
`ENDED` có 2 người được duyệt + lượt giá + bản 1 `DRAFT` (`create_result_scenario`). Kiểm thử trên `dgtt_test`.

## Ghi chú triển khai (Codex)

- Sửa router/schemas/service/repository và thêm permissions.py trong module results, đúng phạm vi. Giữ nguyên chữ ký/hành vi create_draft_result; không sửa modules dùng chung, schema SQL hoặc thư viện.
- Hiện thực GET `/api/v1/sessions/{session_id}/results` (thêm winning_amount/winning_bidder_alias), POST `/api/v1/sessions/{session_id}/results/{result_id}/confirm`, POST `/api/v1/sessions/{session_id}/results` để điều chỉnh. Router chỉ nhận/trả DTO, quyền vai trò qua dependency và phạm vi trong permissions.
- Xác nhận và điều chỉnh khóa dòng phiên trước khi đọc kết quả. Xác nhận chỉ DRAFT, đổi bản CONFIRMED cũ thành SUPERSEDED rồi flush trước khi xác nhận bản mới. Ghi confirmed_by/at và đồng bộ trạng thái tài sản mỗi lần xác nhận; chỉ ghi UPDATE_ASSET_STATUS khi thật sự đổi.
- Điều chỉnh chỉ khi ENDED, bản mới nhất CONFIRMED và không có DRAFT chờ; kiểm tra winning_bid_id thuộc phiên và ACCEPTED, hoặc null. Tạo bản mới với lý do đã strip; giữ nguyên bản CONFIRMED hiện tại và tài sản cho đến khi bản mới được xác nhận.
- Ghi đầy đủ CONFIRM_RESULT/SUPERSEDE_RESULT/UPDATE_ASSET_STATUS/ADJUST_RESULT trước commit, cùng transaction. Không broadcast. DTO không trả định danh người trúng; exception_note chỉ ghi đè khi khóa đó được gửi trong body.
- Mã lỗi: NOT_FOUND, FORBIDDEN/UNAUTHORIZED qua dependency/permissions, RESULT_NOT_DRAFT, SESSION_NOT_ENDED, DRAFT_RESULT_PENDING, NO_CONFIRMED_RESULT, INVALID_WINNING_BID, VALIDATION_ERROR. Không khác đặc tả.
- Ruff check/format sạch. Test không DB: 48 passed, 241 skipped. Toàn bộ test trên dgtt_test_codex: 288 passed, 1 skipped (PDF thật của TASK-004 do thiếu Pango), gồm test API và đồng thời confirm/adjust TASK-005 của Claude. Không có test đỏ.
- Thử nhanh bằng httpx trên dgtt: auctioneer đăng nhập, GET kết quả phiên phụ trách trả 200; confirm result_id không tồn tại trả 404 NOT_FOUND; điều chỉnh với lý do toàn khoảng trắng trả 422 VALIDATION_ERROR. Luồng ghi thành công, phiên bản, tài sản và đồng thời đã kiểm thử bằng dữ liệu giả trên DB riêng.

## Kết quả kiểm thử (Claude)

**Thời điểm:** 2026-11-25 23:20 (giờ Việt Nam) · **Kết luận:** DONE

**Lệnh đã chạy:**

| Lệnh | Kết quả |
|---|---|
| `ruff check .` · `ruff format --check .` | Sạch (108 file) |
| `pytest` (không DB) | 48 đạt, 241 bỏ qua (cần DB) |
| `TEST_DATABASE_URL=…/dgtt_test pytest` (toàn bộ) | **288 đạt**, 1 bỏ qua (PDF thật TASK-004, thiếu Pango), không hồi quy |
| Riêng TASK-005 + `test_bidding_api.py` (luồng đóng phiên tạo DRAFT) | 39/39 đạt |

**Tiêu chí chấp nhận:**

| AC | Kết quả | Test |
|---|---|---|
| AC-1 | Đạt | `test_list_results_with_winner_info`, `test_list_results_permissions`, `test_results_without_token_return_401` |
| AC-2 | Đạt | `test_confirm_draft_with_winner` |
| AC-3 | Đạt | `test_confirm_draft_without_winner` |
| AC-4 | Đạt | `test_confirm_with_exception_note`, `test_confirm_draft_without_winner` (không gửi → giữ ghi chú) |
| AC-5 | Đạt | `test_confirm_not_draft[CONFIRMED/SUPERSEDED]` |
| AC-6 | Đạt | `test_adjust_confirmed_result`, `test_adjust_keep_same_winner` |
| AC-7 | Đạt | `test_confirm_adjusted_supersedes_old` (chuỗi 3 phiên bản: ENDED → UPCOMING → ENDED) |
| AC-8 | Đạt | `test_adjust_when_draft_pending`, `test_adjust_without_any_result`, `test_adjust_session_not_ended` |
| AC-9 | Đạt | `test_adjust_invalid_winning_bid`, `test_adjust_with_new_accepted_bid_of_same_session` |
| AC-10 | Đạt | `test_adjust_validation_error`, `test_confirm_exception_note_too_long` |
| AC-11 | Đạt | `test_confirm_permissions`, `test_adjust_permissions` |
| AC-12 | Đạt | `test_concurrent_confirm_same_draft`, `test_concurrent_adjust` |

**Kiểm tra đầu-cuối bằng request thật (test tạm, đã xoá):** người tham gia trả giá → đấu giá viên đóng phiên sớm có lý do →
hệ thống tự tạo bản 1 `DRAFT` (`NTG-02`) → đấu giá viên xác nhận → 200 `CONFIRMED`, tài sản `ENDED`. Phiên không có lượt
giá: bản 1 `DRAFT` không người trúng → xác nhận → tài sản `UPCOMING`.

**Review code (AGENTS.md Mục 4):**

- Chia lớp đúng; vai trò `AUCTIONEER` qua dependency, phạm vi qua `results/permissions.py` (dùng lại `can_view_internal`,
  `ensure_assigned_auctioneer`). Thứ tự kiểm tra đúng đặc tả.
- Confirm/điều chỉnh khóa dòng phiên trước khi đọc phiên bản; `get_result` dùng `populate_existing` nên lệnh chờ khóa đọc
  đúng trạng thái mới → AC-12 đạt.
- Đổi bản CONFIRMED cũ sang SUPERSEDED và `flush` trước khi xác nhận bản mới (đúng unique index `uq_results_one_confirmed`).
- Log `CONFIRM_RESULT`, `SUPERSEDE_RESULT`, `UPDATE_ASSET_STATUS` (chỉ khi đổi), `ADJUST_RESULT` (có `reason`) trước `commit`.
- Giá trúng/mã người trúng lấy bằng một truy vấn outer join; không trả định danh. `create_draft_result` giữ nguyên.

**Lỗi có sẵn từ trước, không thuộc TASK-005 (không chặn DONE):**

- **Tiền trong JSON bị in dạng số mũ** khi đọc từ DB: `starting_price = "1E+8"`, `bid_increment = "5.00E+6"`,
  `deposit_amount = "2.000E+7"` (GET `/sessions/{id}`), `amount = "1E+8"` (GET `/sessions/{id}/bids`) và
  `winning_amount = "1E+8"` ở API này. Tái hiện: `seed()` rồi `GET /api/v1/sessions/{id}` (khách). Mong đợi `"100000000"`.
  Nguyên nhân khả dĩ: asyncpg trả `Decimal` dạng số mũ, Pydantic tuần tự hoá bằng `str()`. Ảnh hưởng mọi module dùng tiền
  (TASK-003, bidding, TASK-005) nên đã đưa vào Backlog thành task riêng để sửa tập trung, kèm test chung.

## Quyết định của người dùng

_(Trống.)_

## Lịch sử

- 2026-11-25 22:40 | Claude | TODO | Tạo task

- 2026-11-25 22:07 | Codex | IN_PROGRESS | Nhận TASK-005 sau khi bàn giao TASK-004; triển khai theo đặc tả của Claude.

- 2026-11-25 22:11 | Codex | REVIEW | Bàn giao TASK-005; 288 test đạt, 1 PDF thật bỏ qua do môi trường; lint/format sạch.

- 2026-11-25 23:05 | Claude | TESTING | Nhận kiểm thử TASK-005.

- 2026-11-25 23:20 | Claude | DONE | 288/288 test đạt (1 bỏ qua PDF thật); mọi AC đạt. Ghi nhận lỗi định dạng tiền có sẵn → Backlog.
