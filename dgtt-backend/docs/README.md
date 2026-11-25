# docs/ — Giao việc và theo dõi công việc giữa Claude và Codex

```
docs/
├── README.md          File này: cách vận hành hai agent
├── srs.md             Yêu cầu FR-01 – FR-26, NFR-01 – NFR-10 (trích Mục 3.3 báo cáo)
├── TASKS.md           Bảng tổng hợp mọi task (chỉ Claude cập nhật)
└── tasks/
    ├── _TEMPLATE.md   Mẫu file task
    └── TASK-001-*.md  Mỗi task một file
```

## Phân vai

- **Claude** = điều phối + kiểm thử. Viết file task, viết test, chạy test, kết luận DONE hay phải sửa. Không sửa `app/`.
- **Codex** = lập trình. Nhận task, viết code trong `app/`, tự kiểm tra, bàn giao. Không sửa `tests/`, `docs/`.
- **Bạn (người dùng)** = quyết định nghiệp vụ khi agent hỏi (task `BLOCKED`), commit Git khi task `DONE`.

## Cách chạy song song trên hai terminal

**Cả hai terminal phải mở ở thư mục `dgtt-backend/`.** Codex chỉ đọc `AGENTS.md` từ thư mục đang đứng trở lên,
nên nếu mở ở `dau-gia-truc-tuyen/` nó sẽ không thấy quy ước của dự án.

### Chuẩn bị một lần

```powershell
cd "D:\hoc tap\ki 7\CNPM\dau-gia-truc-tuyen\dgtt-backend"
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
docker compose up -d db
docker compose exec db createdb -U dgtt dgtt_test          # của Claude
docker compose exec db createdb -U dgtt dgtt_test_codex    # của Codex
git add -A; git commit -m "Trước khi chạy agent"            # để quay lại được nếu agent sửa sai
```

### Terminal 1 — Codex (lập trình)

```powershell
cd "D:\hoc tap\ki 7\CNPM\dau-gia-truc-tuyen\dgtt-backend"
codex --sandbox workspace-write --ask-for-approval never -c sandbox_workspace_write.network_access=true
```
Rồi gõ: `chạy liên tục` (xem `AGENTS.md` Mục 9). Codex tự làm lần lượt các task, chờ khi Claude đang kiểm thử,
và dừng khi khoảng 30 phút không có việc.

### Terminal 2 — Claude Code (giao việc + kiểm thử)

```powershell
cd "D:\hoc tap\ki 7\CNPM\dau-gia-truc-tuyen\dgtt-backend"
claude
```
Bật chế độ tự duyệt (Shift+Tab đến khi thấy `auto mode on`), rồi gõ:
`/loop 3m Thực hiện một vòng Quy trình E trong CLAUDE.md`
Cứ 3 phút Claude chạy một vòng: kiểm thử task REVIEW → viết test cho task đang làm → lập task mới khi hết việc.

### Theo dõi và can thiệp

- Xem tiến độ: mở `docs/TASKS.md`, hoặc hỏi Claude `Tiến độ thế nào?` ở terminal 2.
- Task `BLOCKED`: trả lời vào mục "Quyết định của người dùng" trong file task, đổi trạng thái về như trước.
- Task `DONE`: xem lại rồi commit `TASK-xxx: <tiêu đề>`.
- Dừng: Codex nhấn `Esc`/`Ctrl+C`; Claude nhấn `Esc` rồi yêu cầu `dừng vòng lặp` (hoặc thoát Claude Code).

### Làm thủ công từng bước (nếu không muốn chạy liên tục)

| Bước | Gõ cho Claude | Gõ cho Codex |
|---|---|---|
| 1 | `Lập task tiếp theo cho module registrations` | |
| 2 | | `Làm TASK-001` |
| 3 (song song bước 2) | `Viết test cho TASK-001 theo đặc tả` | (đang code) |
| 4 | | (bàn giao → REVIEW) |
| 5 | `Kiểm thử TASK-001` | |
| 6a | → DONE: bạn commit `TASK-001: ...` | |
| 6b | → CHANGES_REQUESTED | `Sửa TASK-001 theo kết quả kiểm thử` |

## Cách khác: chạy bằng script (không cần mở terminal agent)

`scripts/auto_run.py` đọc trạng thái trong `docs/tasks/` và tự gọi agent ở chế độ không tương tác:
Codex qua `codex exec`, Claude qua `claude -p`. Mỗi lượt agent chạy xong, script đọc lại trạng thái để chọn việc tiếp theo.

| Trạng thái task | Script gọi |
|---|---|
| `TODO` (đã đủ phụ thuộc) | Codex: làm task. Đồng thời Claude: viết test theo đặc tả |
| `IN_PROGRESS` còn sót từ lần chạy trước | Codex: tiếp tục |
| `REVIEW` / `TESTING` | Claude: kiểm thử (Codex chờ, để test không chạy trên code dở dang) |
| `CHANGES_REQUESTED` | Codex: sửa theo kết quả kiểm thử |
| Còn ít hơn 2 task mở và có `--max-new-tasks` | Claude: lập thêm 1 task từ backlog |
| `BLOCKED` | Bỏ qua, báo lại cuối buổi: bạn trả lời trong file task rồi đổi lại trạng thái |

### Chuẩn bị một lần

1. Cài và đăng nhập hai CLI: `codex` (OpenAI Codex CLI) và `claude` (Claude Code), kiểm tra bằng `codex --version`, `claude --version`.
2. `docker compose up -d db`, tạo `dgtt_test` và `dgtt_test_codex` (xem mục trên), tạo `.venv` và cài `requirements-dev.txt`.
3. **Commit trước khi chạy** để có thể quay lại nếu agent sửa sai.

### Chạy

```bash
python scripts/auto_run.py --dry-run           # xem lượt đầu sẽ làm gì, không gọi agent
python scripts/auto_run.py                     # làm hết các task đang có rồi dừng
python scripts/auto_run.py --max-new-tasks 3   # cho Claude tự lập thêm tối đa 3 task từ backlog
```

Các tuỳ chọn khác: `--max-hours` (mặc định 4), `--timeout-minutes` cho một lượt (45), `--max-fix-rounds` (3),
`--parallel-review` (cho Codex làm task mới trong lúc Claude kiểm thử), `--reset-state`. Xem `--help`.

- Dừng: `Ctrl+C`. Trạng thái nằm trong file task nên lần chạy sau làm tiếp.
- Log từng lượt: `logs/auto_run/*.log` (không đưa lên Git).

### Script tự bảo vệ thế nào

- Mỗi agent được đặt sẵn `TEST_DATABASE_URL` trỏ vào database test riêng của nó.
- Claude chạy với `--permission-mode acceptEdits`, chỉ được phép Read/Edit/Write/Glob/Grep, `pytest`, `ruff`,
  `git status/diff/log`; bị chặn sửa `app/`, `migrations/`, `seeds/`, `sql/`.
- Codex chạy `--sandbox workspace-write`: chỉ ghi được trong thư mục dự án; mở mạng để tới PostgreSQL ở localhost.
- Một lượt thất bại 2 lần thì bỏ qua. Một task bị trả về sửa quá 3 lần thì dừng task đó để bạn xem.
- Agent không commit; bạn xem lại và commit các task DONE.

### Lưu ý

- Cờ dòng lệnh của hai CLI thay đổi theo phiên bản. Nếu lệnh lỗi, sửa `CODEX_CMD` / `CLAUDE_CMD` ở đầu script
  (đối chiếu `codex exec --help`, `claude --help`).
- Trên Windows, nếu sandbox của Codex chặn kết nối tới PostgreSQL hoặc chạy lỗi, hãy chạy script trong WSL.
- Mỗi lượt agent tốn hạn mức (quota) của tài khoản: nên giới hạn bằng `--max-hours` và `--max-new-tasks`.

## Vòng đời trạng thái

```
TODO → IN_PROGRESS → REVIEW → TESTING → DONE
            ▲                     │
            └─ CHANGES_REQUESTED ◄┘
(bất kỳ) → BLOCKED: chờ người dùng / agent kia trả lời câu hỏi ghi trong file task
```

| Chuyển trạng thái | Ai thực hiện |
|---|---|
| (tạo mới) → TODO | Claude |
| TODO / CHANGES_REQUESTED → IN_PROGRESS | Codex |
| IN_PROGRESS → REVIEW | Codex |
| REVIEW → TESTING → DONE / CHANGES_REQUESTED | Claude |
| → BLOCKED, BLOCKED → trạng thái trước đó | Agent gặp vướng mắc, sau khi có câu trả lời |

## Quy ước file task

- **Tên file:** `TASK-<3 chữ số>-<slug-khong-dau>.md`, ví dụ `TASK-004-xac-nhan-ket-qua.md`. Số không tái sử dụng.
- **Ai ghi phần nào:** mỗi agent chỉ ghi phần của mình (xem bảng trong `AGENTS.md` Mục 6). Riêng `## Lịch sử`
  thì cả hai **thêm dòng cuối**, không sửa dòng cũ:
  `- YYYY-MM-DD HH:MM | Claude/Codex/Người dùng | TRẠNG_THÁI | ghi chú`
- **Câu trả lời của người dùng** cho task BLOCKED: ghi vào cuối file task, mục `## Quyết định của người dùng`
  (agent nào được nhờ cũng có thể chép câu trả lời vào đó, kèm ngày giờ).
