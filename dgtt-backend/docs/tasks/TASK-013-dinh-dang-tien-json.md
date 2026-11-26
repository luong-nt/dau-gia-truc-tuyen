# TASK-013: Sửa lỗi tiền trong JSON hiển thị dạng số mũ

- **Trạng thái:** DONE
- **FR/NFR liên quan:** NFR-07 (phản hồi rõ ràng), FR-16, FR-19, FR-21, FR-23
- **Module:** dùng chung (`app/core`), `sessions`, `bidding`, `results` (chỉ schemas)
- **Phụ thuộc:** Không. Các task TASK-006 – TASK-011 phụ thuộc task này vì cùng dùng kiểu tiền chung.
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

Giá trị tiền đọc từ PostgreSQL (`numeric(18,0)`) qua asyncpg có thể là `Decimal('1E+8')`. Pydantic v2 in `Decimal` bằng
`str()`, nên API trả `"starting_price": "1E+8"`, `"bid_increment": "5.00E+6"`, `"deposit_amount": "2.000E+7"`. Giao diện sẽ
hiển thị sai. Task này thêm **một kiểu tiền dùng chung** và áp dụng cho mọi trường tiền trong response REST hiện có.

Phát hiện khi kiểm thử TASK-005 (xem `docs/tasks/TASK-005-xac-nhan-dieu-chinh-ket-qua.md`, mục Kết quả kiểm thử).

## Phạm vi file được sửa (Codex)

- `app/core/money.py` (tạo mới): kiểu `Money` và hàm `format_money`
- `app/modules/sessions/schemas.py`
- `app/modules/bidding/schemas.py`
- `app/modules/results/schemas.py`

Không đổi schema DB, không đổi request (client vẫn gửi số hoặc chuỗi số như hiện tại).

## Đặc tả

### Quy tắc định dạng tiền trong JSON (áp dụng từ task này cho mọi task sau)

- Trường tiền trong **response REST** là **chuỗi chỉ gồm chữ số** (thêm dấu `-` nếu âm): không số mũ, không dấu chấm thập
  phân, không dấu phân cách hàng nghìn. Ví dụ `100000000`, `5000000`, `0`.
- Giá trị `null` giữ nguyên `null`.
- Ví dụ: `Decimal('1E+8')` → `"100000000"`, `Decimal('5.00E+6')` → `"5000000"`, `Decimal('2.000E+7')` → `"20000000"`,
  `Decimal('0')` → `"0"`.

### `app/core/money.py`

- `format_money(value: Decimal | int) -> str`: trả chuỗi theo quy tắc trên (gợi ý: `format(Decimal(value).quantize(Decimal(1)), "f")`).
  Có thể dùng cho CSV.
- `Money`: kiểu `Annotated[Decimal, PlainSerializer(format_money, return_type=str, when_used="json")]` (hoặc tương đương)
  để khai báo trường tiền trong schema output.
- (Tuỳ chọn) `format_vnd(value) -> str`: dạng hiển thị có dấu chấm hàng nghìn, ví dụ `105.000.000`, dùng cho PDF ở TASK-006/011.
  Nếu làm thì: `format_vnd(Decimal('1.05E+8')) == "105.000.000"`.

### Các trường phải đổi sang `Money`

| Schema | Trường |
|---|---|
| `sessions.schemas` (mọi schema output: `SessionOut`, `SessionPublicOut`, …) | `starting_price`, `bid_increment`, `deposit_amount` |
| `bidding.schemas.BidOut`, `PublicBidOut` | `amount` |
| `bidding.schemas.SessionStateOut` | `starting_price`, `bid_increment`, `highest_accepted`, `minimum_next_bid` |
| `results.schemas.ResultOut` | `winning_amount` |

Không đổi kiểu trong request (`PlaceBidRequest.amount`, `PositiveMoney`, `DepositMoney`).

Sự kiện WebSocket đi qua `jsonable_encoder` (in `Decimal` nguyên thành số nguyên JSON) nên **không** thuộc phạm vi task này.

## Tiêu chí chấp nhận

- **AC-1:** `GET /api/v1/sessions/{id}`, `GET /api/v1/sessions`, `GET /api/v1/sessions/manage` trả `starting_price = "100000000"`,
  `bid_increment = "5000000"`, `deposit_amount = "20000000"` với phiên tạo bằng `Decimal` từ DB.
- **AC-2:** `POST /api/v1/sessions` và `PUT /api/v1/sessions/{id}` trả các trường tiền đúng định dạng (kể cả `deposit_amount = 0` → `"0"`).
- **AC-3:** `GET /api/v1/sessions/{id}/state` trả `starting_price`, `bid_increment`, `minimum_next_bid`, `highest_accepted`
  (và `recent_bids[].amount`) dạng chuỗi chữ số; `highest_accepted` là `null` khi chưa có giá.
- **AC-4:** `POST /api/v1/sessions/{id}/bids` (cả lệnh được nhận và bị từ chối) và `GET /api/v1/sessions/{id}/bids` trả `amount` đúng định dạng.
- **AC-5:** `GET /api/v1/sessions/{id}/results` trả `winning_amount = "105000000"`; bản không thành giữ `null`.
- **AC-6:** Không response nào trong các endpoint trên chứa chuỗi `E+` hay giá trị tiền có dấu `.`.
- **AC-7:** Hàm `format_money` đúng các ví dụ trong đặc tả (test unit, không cần DB).
- **AC-8:** Toàn bộ test hiện có vẫn xanh (không hồi quy).

## Kế hoạch kiểm thử (Claude)

| AC | Test | File |
|---|---|---|
| AC-1, AC-6 | `test_session_reads_money_plain` | `tests/api/test_money_format_api.py` |
| AC-2 | `test_session_create_update_money_plain` | `tests/api/test_money_format_api.py` |
| AC-3 | `test_room_state_money_plain` | `tests/api/test_money_format_api.py` |
| AC-4 | `test_bids_money_plain` | `tests/api/test_money_format_api.py` |
| AC-5 | `test_results_money_plain` | `tests/api/test_money_format_api.py` |
| AC-7 | `test_format_money_*` | `tests/unit/test_money.py` |
| AC-8 | toàn bộ bộ test | — |

## Ghi chú triển khai (Codex)

**Người triển khai: Claude** (theo chỉ thị người dùng 2026-11-26 trong `CLAUDE.md`; Codex kiểm thử độc lập).

- **File đã sửa:**
  - `app/core/money.py` (mới): `format_money`, `format_vnd`, kiểu `Money`
    (`Annotated[Decimal, PlainSerializer(format_money, return_type=str, when_used="json")]`).
  - `app/modules/sessions/schemas.py`: `SessionOut` (và `SessionPublicOut` kế thừa): `starting_price`, `bid_increment`,
    `deposit_amount` → `Money`.
  - `app/modules/bidding/schemas.py`: `BidOut.amount`, `PublicBidOut.amount`, `SessionStateOut.starting_price`,
    `bid_increment`, `highest_accepted`, `minimum_next_bid` → `Money`.
  - `app/modules/results/schemas.py`: `ResultOut.winning_amount` → `Money | None`.
- Request giữ nguyên (`PlaceBidRequest.amount`, `PositiveMoney`, `DepositMoney`). WebSocket không đổi.
- `format_vnd` (tuỳ chọn) đã làm, dùng cho PDF ở TASK-006/011.
- **Cách thử nhanh:** `GET /api/v1/sessions/{id}` → `"starting_price": "100000000"`.
- **Tự kiểm tra (2026-11-26 20:50):** `ruff check . && ruff format --check .` sạch.
  `pytest` không DB: 56 passed, 8 failed (đều là test 401 của endpoint thuộc TASK-007/008/010/011/014 chưa làm).
  `dgtt_test`: 303 passed, 2 skipped, 63 failed. `tests/api/test_money_format_api.py` 5/5 và `tests/unit/test_money.py`
  8/8 đạt. 63 ca đỏ đều thuộc task TODO khác: assets (12), asset_owners (6), attachments (9), minutes (10),
  official_result (8), reports (8), report_export (9), TC-RES-003 (1, chờ TASK-006). Không ca nào từng đạt bị hồi quy
  (trước: 290 passed → nay 303).

### Kiểm thử độc lập — Codex, 2026-11-26 20:39

- Đã chạy toàn bộ 368 ca trên `dgtt_test_codex`: **303 passed, 63 failed, 2 skipped**; báo cáo
  `logs/test-results/full-system-06.xml` và `logs/test-results/latest-system-summary.json`.
- **13/13 ca TASK-013 đạt** (5 API định dạng tiền và 8 unit). So với lượt trước không có ca từng đạt bị hồi quy.
  Ruff check và format sạch. Các request vẫn dùng kiểu cũ; response dùng Money đúng phạm vi.
- **TASK-013 đạt kiểm thử độc lập, đủ điều kiện hoàn tất và mở phụ thuộc cho các task tiếp theo.**
  63 ca đỏ thuộc các task chưa triển khai (006/007/008/009/010/011/014 và TC-RES-003), không phải hồi quy TASK-013.
- Trong lúc chạy, mã module results đã có thay đổi tiếp cho TASK-006. Lượt trên nạp mã ở đầu tiến trình;
  Codex sẽ kiểm thử TASK-006 bằng lượt mới sau khi bàn giao.

## Kết quả kiểm thử (Claude)

- **Claude tự kiểm (2026-11-26 20:50):** ruff sạch; `tests/api/test_money_format_api.py` 5/5, `tests/unit/test_money.py` 8/8;
  toàn bộ `dgtt_test` 303 passed, 2 skipped, 63 failed (đều thuộc task TODO khác, xem Ghi chú triển khai).
- **Codex kiểm thử độc lập (Lịch sử 20:39):** 13/13 ca của task đạt; 303 test đạt toàn hệ thống, không hồi quy.

| AC | Kết quả | Test |
|---|---|---|
| AC-1 | Đạt | `test_session_reads_money_plain` |
| AC-2 | Đạt | `test_session_create_update_money_plain` |
| AC-3 | Đạt | `test_room_state_money_plain` |
| AC-4 | Đạt | `test_bids_money_plain` |
| AC-5 | Đạt | `test_results_money_plain` |
| AC-6 | Đạt | các test API trên (kiểm `E+`) |
| AC-7 | Đạt | `tests/unit/test_money.py` |
| AC-8 | Đạt | toàn bộ bộ test, không ca nào hồi quy |

**Kết luận:** DONE.

## Quyết định của người dùng

_(Không có.)_

## Lịch sử

- 2026-11-26 09:00 | Claude | TODO | Tạo task từ lỗi phát hiện khi kiểm thử TASK-005
- 2026-11-26 20:40 | Claude | IN_PROGRESS | Claude nhận triển khai theo chỉ thị người dùng trong CLAUDE.md
- 2026-11-26 20:52 | Claude | REVIEW | Bàn giao, chờ Codex kiểm thử độc lập

- 2026-11-26 20:39 | Codex | REVIEW | Kiểm thử độc lập TASK-013 đạt 13/13; 303 test đạt toàn hệ thống, không hồi quy; phản hồi cho Claude hoàn tất.
- 2026-11-26 21:10 | Claude | DONE | Đọc phản hồi Codex (13/13 đạt, không hồi quy); mọi AC đạt
