# DGTT Backend — Hệ thống quản lý đấu giá trực tuyến

Backend viết bằng **Python 3.12 + FastAPI**, dùng **PostgreSQL 16**. Schema chuẩn là file
[`sql/dgtt_schema_postgresql.sql`](sql/dgtt_schema_postgresql.sql) (10 bảng).

## 1. Chạy nhanh bằng Docker (khuyên dùng, nhất là trên Windows)

```bash
docker compose up --build
```

- API: http://localhost:8000 — tài liệu Swagger: http://localhost:8000/docs
- Lần đầu, tạo dữ liệu mẫu (mở terminal khác):

```bash
docker compose exec backend python -m seeds.seed_dev
```

## 2. Chạy trực tiếp trên máy (để code và debug)

```bash
# 1) Tạo môi trường ảo và cài thư viện
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements-dev.txt

# 2) Cấu hình
copy .env.example .env          # Windows  (macOS/Linux: cp .env.example .env)

# 3) Chỉ chạy PostgreSQL bằng Docker
docker compose up -d db

# 4) Tạo bảng từ file SQL chuẩn và nạp dữ liệu mẫu
alembic upgrade head
python -m seeds.seed_dev

# 5) Chạy server (1 worker)
uvicorn app.main:app --reload
```

**Tài khoản mẫu** (mật khẩu chung `Matkhau@123`): `admin`, `staff`, `auctioneer`, `bidder1`, `bidder2`.
Seed tạo sẵn phiên **PDG-1 đang diễn ra** (giá khởi điểm 100.000.000 đ, bước giá 5.000.000 đ),
`bidder1` = `NTG-01`, `bidder2` = `NTG-02` đã được duyệt.

> Xuất PDF dùng WeasyPrint, cần thư viện Pango. Trên Windows nên chạy phần này qua Docker;
> các chức năng khác chạy bình thường không cần Pango.

## 3. Chạy test

```bash
pytest                       # test không cần DB (unit, 401/422)
```

Test cần DB (đánh dấu `@pytest.mark.db`) chạy trên một **database riêng** — database này bị xóa sạch
và tạo lại mỗi lần chạy:

```bash
docker compose exec db createdb -U dgtt dgtt_test
# Windows PowerShell:
$env:TEST_DATABASE_URL="postgresql+asyncpg://dgtt:dgtt@localhost:5432/dgtt_test"; pytest
# macOS/Linux:
TEST_DATABASE_URL=postgresql+asyncpg://dgtt:dgtt@localhost:5432/dgtt_test pytest
```

Kiểm thử tải (NFR-01, NFR-03): `locust -f tests/load/locustfile.py --host http://localhost:8000`

Lint và format: `ruff check . && ruff format .` (cài hook: `pre-commit install`).

## 4. Kiến trúc

Một ứng dụng duy nhất, chia **module theo nghiệp vụ**; trong mỗi module chia lớp
**Router (API) → Service (nghiệp vụ) → Repository (truy vấn)**. Models ORM đặt chung ở `app/db/models/`,
mỗi file ứng với một bảng trong SQL.

| Module | Bảng chính | FR | Tình trạng |
|---|---|---|---|
| `auth` | users | FR-01 – 03 | ✅ Xong: đăng ký, đăng nhập, đăng xuất, hồ sơ, đổi mật khẩu |
| `users` | users | FR-04 | ✅ Xong: tìm kiếm, tạo tài khoản nội bộ, đổi vai trò, khóa/mở |
| `sessions` | auction_sessions | FR-08, 09, 16, 17 | 🟡 Xong điều hành trạng thái (công khai, mở, tạm dừng, tiếp tục, đóng, hủy); còn tạo/sửa phiên, thông báo |
| `bidding` | bids | FR-18 – 21 | ✅ Xong: gửi giá có khóa, chống gửi trùng, trạng thái phòng, lịch sử, WebSocket |
| `results` | auction_results | FR-22, 23 | 🟡 Xong tạo kết quả DRAFT khi đóng phiên; còn xác nhận, điều chỉnh, biên bản |
| `assets` | asset_owners, assets, attachments | FR-05 – 07 | ⬜ Khung + danh sách TODO |
| `registrations` | registrations, registration_reviews, attachments | FR-10 – 15 | ⬜ Khung + hàm kiểm tra 3 bước, sinh mã ẩn danh |
| `reports` | đọc mọi bảng, activity_logs | FR-24 – 26 | ⬜ Khung + xuất CSV/PDF |

Mỗi file router/service còn dang dở có danh sách `TODO(FR-xx)` ghi rõ endpoint và quy tắc cần làm.

### Thành phần dùng chung (`app/core/`)

- `deps.py`: `get_current_user`, `require_roles(...)`. Mỗi request hợp lệ trả kèm token mới trong header
  `X-Access-Token` (gia hạn trượt 30 phút — NFR-04). Frontend nên thay token cũ bằng token này.
- `audit.py`: `log_activity(...)` — gọi **trong cùng transaction** với thao tác nghiệp vụ.
- `exceptions.py`: mọi lỗi trả về dạng `{"code", "message", "details"}`, thông điệp tiếng Việt.
- `realtime.py`: quản lý WebSocket theo phòng; chỉ phát sự kiện **sau khi commit**.
- `storage.py`: lưu tệp upload trong `storage/`, không mở thư mục tĩnh (có giấy tờ định danh).
- `clock.py`: database và backend thống nhất dùng **UTC**; frontend đổi sang GMT+7 khi hiển thị.

### Luồng trả giá (`app/modules/bidding/service.py`)

1. Khóa dòng phiên `SELECT … FOR UPDATE` → các lệnh cùng phiên xếp hàng tuần tự.
2. `transaction_code` đã tồn tại → trả lại kết quả cũ (client sinh UUID cho mỗi lệnh).
3. Kiểm tra phiên `IN_PROGRESS`, chưa quá `end_time`, hồ sơ `APPROVED`, mức giá theo
   `rules.py`: P = P0 + k × Δ, lượt đầu được bằng P0, lượt sau phải lớn hơn giá cao nhất.
4. Ghi `ACCEPTED` hoặc `REJECTED` (kèm lý do) với `sequence_no` tiếp theo → COMMIT → phát `bid.accepted`.

### Phòng đấu giá realtime

```
ws://localhost:8000/ws/sessions/{session_id}?token=<JWT>
```

Server gửi `session.snapshot` khi vừa kết nối, sau đó `bid.accepted` và `session.status_changed`.
Lệnh trả giá gửi qua REST `POST /api/v1/sessions/{id}/bids`. Khi kết nối lại, gọi
`GET /api/v1/sessions/{id}/state` hoặc kết nối WebSocket lại để nhận snapshot mới.

### Bộ lập lịch (`app/jobs/session_jobs.py`, chạy mỗi giây)

- `OPEN_FOR_REGISTRATION` quá `registration_deadline` → `UPCOMING`
- `IN_PROGRESS` đến `end_time` → `ENDED` + tạo `auction_results` bản 1 (`DRAFT`)

> Vì WebSocket và scheduler nằm trong bộ nhớ tiến trình, **chỉ chạy uvicorn với 1 worker**.

## 5. Các quy ước nghiệp vụ đã thống nhất

1. Lượt giá đầu **được bằng** giá khởi điểm (áp dụng chung, schema không có cột cấu hình riêng).
2. Trạng thái phiên: DRAFT → (Nhân viên công khai) OPEN_FOR_REGISTRATION → (tự động) UPCOMING →
   (Đấu giá viên mở, khi đã đến giờ) IN_PROGRESS ⇄ PAUSED → ENDED; trước ENDED có thể CANCELLED (có lý do).
3. Hồ sơ quá hạn bổ sung: chỉ chặn nộp lại, không tự đổi trạng thái; nhân viên từ chối thủ công.
4. Trạng thái tài sản: tạo mới UPCOMING; phiên IN_PROGRESS → IN_AUCTION; kết quả xác nhận có người
   trúng → ENDED; không thành/phiên hủy → UPCOMING; nhân viên đặt SUSPENDED_CANCELLED.
5. `bidder_alias` sinh khi duyệt hồ sơ, dạng `NTG-01`, `NTG-02`… trong từng phiên.
6. Không có phân công xét hồ sơ: STAFF nào cũng xét được mọi hồ sơ.
7. Thông báo cho người tham gia lấy từ `registration_reviews`, không thêm bảng.
8. Kết quả đấu giá: hệ thống chỉ tạo DRAFT; Đấu giá viên phụ trách xác nhận; điều chỉnh = phiên bản mới.

## 6. Quy ước code

- Muốn đổi schema: sửa `sql/dgtt_schema_postgresql.sql` trước, rồi viết migration mới trong
  `migrations/versions/`. **Không** dùng `alembic revision --autogenerate` để tự sinh bảng.
- Enum trong `app/db/enums.py` phải khớp đúng ràng buộc `CHECK` trong SQL.
- Bảng `bids` và `activity_logs` chỉ ghi thêm: không viết hàm sửa/xóa.
- File/hàm `snake_case`, class `PascalCase`; mỗi module làm trên một nhánh Git riêng (ví dụ `feature/registrations`).

## 7. Cấu trúc thư mục

```
dgtt-backend/
├── app/
│   ├── main.py                 # tạo app, gắn router, khởi động scheduler
│   ├── core/                   # config, security, deps, exceptions, audit, realtime, scheduler, storage, pagination, clock
│   ├── db/                     # base, session, enums, models/ (10 bảng)
│   ├── modules/                # auth, users, assets, sessions, registrations, bidding, results, reports
│   ├── jobs/session_jobs.py    # job tự chuyển trạng thái, đóng phiên
│   └── templates/              # mẫu HTML xuất PDF
├── migrations/                 # Alembic; 0001 chạy file SQL chuẩn
├── sql/dgtt_schema_postgresql.sql
├── seeds/seed_dev.py           # dữ liệu mẫu
├── tests/                      # unit/, api/, concurrency/, load/
├── storage/                    # tệp upload (không đưa lên Git)
├── docker-compose.yml, Dockerfile, alembic.ini, pyproject.toml
└── requirements.txt, requirements-dev.txt, .env.example
```

## 8. Làm việc với hai agent (Claude + Codex)

- `AGENTS.md`: quy ước chung + hướng dẫn cho **Codex** (lập trình).
- `CLAUDE.md`: hướng dẫn cho **Claude** (giao việc + kiểm thử), import `AGENTS.md`.
- `docs/`: `srs.md` (yêu cầu), `TASKS.md` (bảng công việc), `tasks/TASK-xxx-*.md` (mỗi việc một file).
- Cách vận hành, vòng đời trạng thái và ví dụ câu lệnh: xem `docs/README.md`.
- Chạy tự động không cần gõ lệnh từng bước: `python scripts/auto_run.py` (chi tiết trong `docs/README.md`).
