# AGENTS.md — DGTT Backend

Dự án có **hai agent làm việc song song** trên cùng thư mục này:

| Agent | Vai trò | Được sửa | Đọc thêm |
|---|---|---|---|
| **Codex** | Lập trình viên: hiện thực các task được giao | `app/`, `migrations/`, `seeds/`, `requirements*.txt` | File này |
| **Claude** | Điều phối (giao việc) + Kiểm thử (QA) | `tests/`, `docs/`, `AGENTS.md`, `CLAUDE.md` | `CLAUDE.md` |

Mục 1–6 là quy ước chung cho **mọi agent**. Mục 7–8 là hướng dẫn riêng cho **Codex**.
Mọi trao đổi giữa hai agent đi qua **file task trong `docs/tasks/`** (xem `docs/README.md`).

---

## 1. Dự án

Hệ thống quản lý đấu giá trực tuyến **DGTT** (bài tập lớn Công nghệ phần mềm).

- **Stack:** Python 3.12, FastAPI, PostgreSQL 16, SQLAlchemy 2 (async, asyncpg), Alembic, Pydantic v2,
  pwdlib (Argon2), PyJWT, APScheduler, WebSocket, Jinja2 + WeasyPrint, pytest, ruff.
- **Nguồn chuẩn, theo thứ tự ưu tiên:**
  1. `sql/dgtt_schema_postgresql.sql`: schema 10 bảng. Code phải khớp schema, **không** ngược lại.
  2. `docs/srs.md`: yêu cầu chức năng FR-01 – FR-26 và phi chức năng NFR-01 – NFR-10.
  3. Mục 5 của file này: các quy ước nghiệp vụ nhóm đã chốt.
  4. File task đang làm trong `docs/tasks/`.
- Giao diện, thông báo lỗi, comment và docstring viết **tiếng Việt có dấu**. Tên biến, hàm, class viết tiếng Anh.

## 2. Bản đồ code

```
app/main.py                 tạo app, gắn router (/api/v1), WebSocket, scheduler
app/core/                   dùng chung: config, security, deps, exceptions, audit, realtime,
                            scheduler, storage, pagination, clock
app/db/models/              mỗi file = 1 bảng trong SQL;  app/db/enums.py khớp CHECK trong SQL
app/modules/<module>/       router.py (API) → service.py (nghiệp vụ) → repository.py (truy vấn)
                            + schemas.py (DTO), permissions.py (phạm vi dữ liệu)
app/jobs/session_jobs.py    job mỗi giây: tự đóng nhận hồ sơ, tự đóng phiên, tạo kết quả DRAFT
migrations/versions/        0001 chạy file SQL chuẩn
seeds/seed_dev.py           dữ liệu mẫu; hàm seed(db, prefix=...) dùng lại trong test
tests/                      unit/, api/, concurrency/, load/   (do Claude quản lý)
docs/                       srs.md, TASKS.md, tasks/TASK-xxx-*.md  (do Claude quản lý)
```

Tình trạng module (cập nhật chi tiết trong `docs/TASKS.md`):

| Module | Đã có |
|---|---|
| `auth`, `users`, `bidding` | Đầy đủ |
| `sessions` | Điều hành trạng thái; còn thiếu tạo/sửa phiên, thông báo |
| `results` | Tạo DRAFT khi đóng phiên; còn thiếu xác nhận, điều chỉnh, biên bản |
| `assets`, `registrations`, `reports` | Khung + `TODO(FR-xx)` |

## 3. Lệnh thường dùng

Chạy trong thư mục `dgtt-backend/`, đã kích hoạt `.venv`.

```bash
docker compose up -d db                       # chỉ chạy PostgreSQL
alembic upgrade head                          # tạo bảng (DB theo DATABASE_URL trong .env)
python -m seeds.seed_dev                      # dữ liệu mẫu, mật khẩu Matkhau@123
uvicorn app.main:app --reload                 # server, 1 worker; Swagger ở /docs

ruff check . && ruff format .                 # lint + format (bắt buộc trước khi bàn giao)
pytest                                        # test không cần DB (unit, 401/422)
```

Chạy test có DB (đánh dấu `@pytest.mark.db`). Database test bị **xóa sạch và tạo lại** mỗi lần chạy,
nên **mỗi agent dùng một database test riêng**:

| Agent | Database test |
|---|---|
| Claude | `dgtt_test` |
| Codex | `dgtt_test_codex` |

```powershell
# Tạo một lần:  docker compose exec db createdb -U dgtt dgtt_test_codex
$env:TEST_DATABASE_URL="postgresql+asyncpg://dgtt:dgtt@localhost:5432/dgtt_test_codex"; pytest
```
```bash
TEST_DATABASE_URL=postgresql+asyncpg://dgtt:dgtt@localhost:5432/dgtt_test_codex pytest
```

**Không bao giờ** chạy test với `TEST_DATABASE_URL` trỏ vào database của agent kia, hoặc vào `dgtt` (database dev).

## 4. Quy ước kỹ thuật bắt buộc

1. **Schema:**
   - Không tự sửa `sql/dgtt_schema_postgresql.sql`. Không dùng `alembic revision --autogenerate`.
   - Cần đổi schema thì ghi đề xuất vào file task, đặt `BLOCKED`, chờ người duyệt.
2. **Chia lớp:**
   - Router chỉ nhận/trả DTO và gọi service.
   - Nghiệp vụ, transaction, `commit` nằm trong service.
   - Truy vấn nằm trong repository.
   - Service được gọi service của module khác; không gọi ngược từ tầng dưới lên tầng trên.
3. **Enum:** dùng `app/db/enums.py`, không viết chuỗi trạng thái trực tiếp trong code.
4. **Lỗi:** chỉ ném các lớp trong `app/core/exceptions.py` (`NotFoundError`, `ForbiddenError`,
   `ConflictError`, `BusinessRuleError`…), kèm `message` tiếng Việt và `code` dạng `UPPER_SNAKE_CASE`.
   Client luôn nhận `{"code", "message", "details"}`.
5. **Phân quyền (NFR-05):**
   - Kiểm tra vai trò bằng `require_roles(...)`.
   - Kiểm tra phạm vi dữ liệu trong `permissions.py` của module: đúng chủ hồ sơ, đúng đấu giá viên được phân công.
   - Chưa đăng nhập → 401. Không đủ quyền → 403.
6. **Nhật ký (FR-26):**
   - Mọi thao tác quan trọng gọi `log_activity(...)` **trước khi commit**, trong cùng transaction.
   - Đổi giá trị thì ghi `field_name`, `old_value`, `new_value`, và `reason` nếu có.
7. **Chỉ ghi thêm:** không viết hàm UPDATE/DELETE cho bảng `bids` và `activity_logs`.
8. **Realtime:** chỉ gọi `manager.broadcast(...)` **sau khi** commit thành công.
9. **Thời gian:** dùng `app.core.clock.utcnow()` (UTC, không kèm múi giờ). Không dùng `datetime.now()`.
10. **Khóa khi tranh chấp:** thao tác cần đọc-rồi-ghi theo phiên (nhận giá, đổi trạng thái, cấp `bidder_alias`)
    phải khóa dòng phiên bằng `sessions.repository.get_session_for_update`.
11. **File upload:**
    - Chỉ qua `app.core.storage.save_upload`.
    - Tải tệp về phải qua endpoint có kiểm tra quyền, dùng `resolve_path`.
    - Không mở thư mục tĩnh.
12. **Phân trang:** danh sách có thể dài thì dùng `Pagination` và `Page[T]` trong `app/core/pagination.py`.
13. **Vận hành:** backend chạy **1 worker** (WebSocket và scheduler nằm trong bộ nhớ tiến trình).
14. **Code:** ruff sạch (line-length 120), có type hint, không để `print` hay code debug.

## 5. Quy ước nghiệp vụ đã chốt

1. **Quy tắc giá (FR-20):**
   - P = P0 + k × Δ.
   - Lượt đầu **được bằng** giá khởi điểm.
   - Lượt sau phải **lớn hơn** giá cao nhất đã nhận.
   - Lệnh bị từ chối vẫn ghi vào `bids` (`REJECTED`, có `rejection_reason`).
2. **Trạng thái phiên:**
   - DRAFT → (Nhân viên công khai) OPEN_FOR_REGISTRATION.
   - OPEN_FOR_REGISTRATION → (tự động khi qua hạn hồ sơ) UPCOMING.
   - UPCOMING → (Đấu giá viên được phân công mở, khi đã đến giờ) IN_PROGRESS.
   - IN_PROGRESS ⇄ PAUSED.
   - IN_PROGRESS/PAUSED → ENDED: tự động khi đến `end_time`, hoặc đóng sớm có lý do.
   - Mọi trạng thái trước ENDED → CANCELLED, có lý do.
   - Xem `app/modules/sessions/state_machine.py`.
3. **Trạng thái hồ sơ:**
   - PENDING → APPROVED, chỉ khi DOCUMENT_CHECK, ELIGIBILITY_CHECK và DEPOSIT_CHECK **mới nhất** đều PASSED.
   - PENDING → NEEDS_SUPPLEMENT, có lý do và hạn bổ sung.
   - PENDING → REJECTED, có lý do.
   - NEEDS_SUPPLEMENT → PENDING khi người tham gia nộp lại **trước hạn**.
4. **Hồ sơ quá hạn bổ sung:** chỉ chặn nộp lại, **không** tự đổi trạng thái; nhân viên từ chối thủ công.
5. **`bidder_alias`:** sinh lúc duyệt, dạng `NTG-01`, `NTG-02`… tăng dần trong từng phiên.
6. **Xét duyệt hồ sơ:** không có phân công; **STAFF nào cũng xét được mọi hồ sơ**.
7. **Trạng thái tài sản:**
   - Tạo mới: UPCOMING.
   - Phiên IN_PROGRESS: IN_AUCTION.
   - Kết quả CONFIRMED có người trúng: ENDED.
   - Đấu giá không thành hoặc phiên hủy: UPCOMING.
   - Nhân viên chủ động: SUSPENDED_CANCELLED.
8. **Kết quả đấu giá:**
   - Hệ thống chỉ tạo bản 1 ở trạng thái DRAFT.
   - Đấu giá viên phụ trách xác nhận → CONFIRMED.
   - Điều chỉnh = tạo phiên bản mới có lý do; khi bản mới được xác nhận, bản CONFIRMED cũ → SUPERSEDED.
9. **Thông báo cho người tham gia (FR-13):** lấy từ `registration_reviews`, không thêm bảng.
10. **Hết hạn đăng nhập:** JWT 30 phút; mỗi response hợp lệ trả kèm token mới trong header `X-Access-Token`.
11. **Dữ liệu định danh** (`submitted_id_number`, địa chỉ, số điện thoại): **không** trả trong API công khai
    hoặc trong phòng đấu giá. Phòng đấu giá chỉ dùng `bidder_alias`.

Gặp tình huống không có trong SRS và mục này: **không tự quyết**. Ghi câu hỏi vào file task và đặt `BLOCKED`.

## 6. Quy trình làm việc theo task

Chi tiết và mẫu file ở `docs/README.md` và `docs/tasks/_TEMPLATE.md`. Tóm tắt:

**Vòng đời trạng thái của một task:**

```
TODO ──(Codex nhận)──► IN_PROGRESS ──(Codex bàn giao)──► REVIEW ──(Claude nhận test)──► TESTING
                           ▲                                                            │
                           └──────────── CHANGES_REQUESTED ◄──(Claude: chưa đạt)─────────┤
                                                                                        └──(Claude: đạt)──► DONE
Bất kỳ trạng thái nào ──► BLOCKED (ghi rõ câu hỏi/lý do, chờ người hoặc agent kia trả lời)
```

**Ai được ghi phần nào trong file task:**

| Phần trong file task | Codex | Claude |
|---|---|---|
| Dòng `Trạng thái` | TODO→IN_PROGRESS, CHANGES_REQUESTED→IN_PROGRESS, IN_PROGRESS→REVIEW, →BLOCKED | REVIEW→TESTING, TESTING→DONE / CHANGES_REQUESTED, →BLOCKED |
| Mô tả, Phạm vi, Đặc tả API, Tiêu chí chấp nhận (AC), Kế hoạch kiểm thử | Chỉ đọc | Ghi |
| `## Ghi chú triển khai (Codex)` | Ghi | Chỉ đọc |
| `## Kết quả kiểm thử (Claude)` | Chỉ đọc | Ghi |
| `## Lịch sử` | Thêm dòng cuối | Thêm dòng cuối |

**Các quy tắc khác:**
- **Bảng tổng hợp:** chỉ Claude sửa `docs/TASKS.md`. Codex chỉ đổi trạng thái trong file task, Claude sẽ đồng bộ sang bảng.
- **Thư mục:** không agent nào sửa thư mục của agent kia (xem bảng đầu file).
  - Codex thấy test sai → ghi vào "Ghi chú triển khai".
  - Claude thấy lỗi code → ghi vào "Kết quả kiểm thử".
- **Git:** agent **không** `commit`, `push`, `checkout`, `reset`, `stash`, `rebase`. Người dùng tự commit khi task DONE,
  với message dạng `TASK-001: <tiêu đề>`. Agent chỉ được đọc (`git status`, `git diff`, `git log`).
- **Dòng lịch sử:** `- 2026-11-25 20:30 | Codex | IN_PROGRESS | <ghi chú ngắn>`, theo giờ Việt Nam.
- **Chạy tự động** (`scripts/auto_run.py`, xem `docs/README.md`): agent được gọi không tương tác, **không có ai trả lời**.
  Không hỏi lại; cần quyết định thì ghi câu hỏi vào file task, đặt `BLOCKED` rồi kết thúc lượt.
  Khi biến môi trường `TEST_DATABASE_URL` đã được đặt sẵn, dùng đúng giá trị đó, chỉ cần chạy `pytest`.

---

## 7. Hướng dẫn cho Codex (lập trình viên)

Khi được yêu cầu "làm TASK-xxx", hoặc "làm task tiếp theo" (chọn task `TODO` hay `CHANGES_REQUESTED`
có số nhỏ nhất trong `docs/tasks/` mà mục "Phụ thuộc" đã DONE):

1. **Nhận task:**
   - Đọc toàn bộ file task và các FR được nhắc tới trong `docs/srs.md`.
   - Đổi `Trạng thái` sang `IN_PROGRESS`, thêm một dòng vào `## Lịch sử`.
   - Mỗi lần chỉ làm **một** task.
2. **Hiện thực:**
   - Chỉ sửa file trong mục "Phạm vi file được sửa" của task.
   - Cần sửa file ngoài phạm vi (kể cả `app/core/`) thì ghi lý do vào "Ghi chú triển khai". Nếu ảnh hưởng module khác, đặt `BLOCKED`.
   - Bám đúng "Đặc tả API": method, đường dẫn, tên trường, mã lỗi. Claude viết test theo đúng đặc tả này, **song song** với lúc bạn code.
   - Thay các `TODO(FR-xx)` đã làm xong bằng code thật; xóa comment TODO tương ứng.
3. **Tự kiểm tra trước khi bàn giao:**
   - `ruff check . && ruff format .` sạch.
   - `pytest` (không DB) xanh.
   - Chạy test có DB trên **`dgtt_test_codex`**: toàn bộ test hiện có, kể cả test Claude đã viết cho task này. Test của task chưa có thì bỏ qua bước này.
   - Gọi thử API bằng Swagger (`/docs`) hoặc httpx trên database dev `dgtt`.
4. **Bàn giao:** điền `## Ghi chú triển khai (Codex)` gồm:
   - file đã sửa;
   - endpoint đã làm;
   - mã lỗi đã dùng;
   - điểm khác với đặc tả (nếu có) và lý do;
   - cách thử nhanh;
   - test nào của Claude đang đỏ và vì sao (nếu có).

   Sau đó đổi `Trạng thái` sang `REVIEW` và thêm dòng `## Lịch sử`.
5. **Khi task bị `CHANGES_REQUESTED`:**
   - Đọc `## Kết quả kiểm thử (Claude)`, sửa đúng các lỗi được nêu.
   - Ghi thêm một mục "Lần sửa n" vào ghi chú triển khai.
   - Bàn giao lại (`REVIEW`).
6. **Không được làm:**
   - sửa `tests/`, `docs/` (trừ hai phần của mình trong file task), `sql/`;
   - tự ý đổi quy ước ở Mục 4–5;
   - commit Git;
   - chạy test trên `dgtt_test`.

## 8. Checklist "xong" của Codex (trước khi đặt REVIEW)

- [ ] Mọi tiêu chí chấp nhận (AC) trong task đã được hiện thực.
- [ ] Đủ kiểm tra vai trò + phạm vi dữ liệu. Đúng mã lỗi 401/403/404/409/422 như đặc tả.
- [ ] Có `log_activity` cho thao tác ghi quan trọng.
- [ ] Không lộ dữ liệu định danh ngoài phạm vi được phép.
- [ ] Ruff sạch, `pytest` xanh, test có DB trên `dgtt_test_codex` xanh (hoặc đã giải thích test đỏ).
- [ ] Đã điền "Ghi chú triển khai" và dòng "Lịch sử".

## 9. Chế độ làm việc liên tục của Codex (khi người dùng gõ "chạy liên tục")

Làm việc không cần người dùng gõ thêm, lặp lại các bước sau:

1. Đọc dòng `Trạng thái` của mọi file `docs/tasks/TASK-*.md`.
2. Chọn việc theo thứ tự (mỗi lần **một** task, làm đến khi đặt `REVIEW` theo Mục 7):
   1. task `CHANGES_REQUESTED` → sửa theo "Kết quả kiểm thử (Claude)";
   2. task `IN_PROGRESS` (của bạn, đang dở) → làm tiếp;
   3. task `TODO` có số nhỏ nhất mà mọi task trong "Phụ thuộc" đã `DONE`.
3. Nếu đang có task `REVIEW`/`TESTING` (Claude đang kiểm thử) hoặc không có việc phù hợp: **chờ 2 phút**
   (`Start-Sleep -Seconds 120` trong PowerShell, `sleep 120` trong bash) rồi quay lại bước 1.
4. **Dừng** khi: 15 lần kiểm tra liên tiếp (khoảng 30 phút) không có việc; hoặc mọi task đều `DONE`/`BLOCKED`;
   hoặc gặp lỗi môi trường không tự khắc phục được (thiếu thư viện, không kết nối được PostgreSQL). Khi dừng, in tóm tắt:
   task đã bàn giao, task đang chờ ai, lỗi môi trường (nếu có).
5. Không hỏi lại người dùng. Cần quyết định thì ghi câu hỏi vào file task, đặt `BLOCKED`, chuyển sang task khác.
6. Không tự cài đặt lại môi trường ở ngoài `.venv` của dự án, không dùng Docker; PostgreSQL do người dùng bật sẵn.

