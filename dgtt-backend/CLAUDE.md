@AGENTS.md

## Chỉ thị của người dùng ngày 2026-11-26 — Claude nhận triển khai

Người dùng đã yêu cầu trực tiếp: **"Giao cho CLAUDE CLI đang chạy các task còn lại."**
Phân công cho đợt này: **Claude triển khai các task còn lại; Codex theo dõi và kiểm thử độc lập.**
Phân công này thay thế giới hạn vai trò chỉ điều phối/QA và cấm sửa `app/` ở các mục bên dưới đối với đợt công việc này.

### Việc cần thực hiện ngay trong phiên CLI hiện tại

1. Làm việc trong `dgtt-backend/`. Đọc trạng thái gốc của các file `docs/tasks/TASK-*.md`.
2. Nhận **TASK-013** trước (đang TODO, đã có test), đổi sang IN_PROGRESS và triển khai thật `app/core/money.py` cùng
   các schema output trong đúng phạm vi task. Các task sau cần kiểu tiền chung này.
3. Tiếp tục lần lượt các task đủ phụ thuộc: **TASK-006, TASK-007, TASK-014, TASK-008, TASK-009, TASK-010, TASK-011**.
   Ưu tiên CHANGES_REQUESTED trước việc mới; mỗi lần chỉ sửa một task và tôn trọng phạm vi file/đặc tả của task đó.
4. Claude được sửa mã ứng dụng trong phạm vi từng task, test và tài liệu liên quan; được điền phần Ghi chú triển khai
   dù tiêu đề mẫu cũ ghi Codex (ghi rõ tác giả Claude). Không chờ Codex nhận triển khai các task TODO của đợt này.
5. Dùng dữ liệu mock/fixtures cho kiểm thử khi cần theo quyền người dùng đã cấp. Kiểm thử nghiệp vụ qua API và DB thật;
   không thay phản hồi API thành giả để che phần chức năng chưa có. Không hạ tiêu chí TC-REV-002/TC-RES-003 để làm xanh test.
6. Claude dùng `.venv` và database **dgtt_test**; Codex dùng **dgtt_test_codex**. Không chạy test trên database dev dgtt.
   Giữ nguyên quy ước schema, transaction, khóa phiên, audit, phân quyền, enum và UTC trong AGENTS.md.
7. Tự kiểm tra và ghi kết quả rõ ràng rồi bàn giao REVIEW. Codex sẽ chạy kiểm thử độc lập và ghi phản hồi ở phần của mình;
   với vai trò kiểm thử trong đợt này, Codex được đặt CHANGES_REQUESTED khi có lỗi cần Claude sửa.
   Đọc phản hồi, sửa lỗi cần thiết và cập nhật DONE khi AC đạt và các phần đã triển khai không bị hồi quy; các test của
   task TODO khác chưa triển khai phải được liệt kê riêng, không giữ vô hạn task hiện tại vì những lỗi đó.
8. **TASK-012 đã có quyết định của người dùng lúc 2026-11-26 21:04: phương án A, cộng bù đúng thời gian tạm dừng.**
   Đọc mục Quyết định của người dùng trong file task; hoàn thiện đặc tả API, phạm vi sửa, AC và test, rồi chuyển TODO
   và triển khai (thêm TASK-012 vào đợt này, sau các task đã đủ đặc tả). Không tiếp tục chờ chọn A/B/C.
   PDF thật trên Windows có thể thiếu Pango: ghi rõ khác biệt lỗi môi trường với lỗi endpoint/chức năng.
9. Không commit/push, không dùng Docker, không cài lại môi trường ngoài `.venv`. Tiếp tục đến khi các task của đợt này
   DONE hoặc BLOCKED với lý do cụ thể cần người dùng quyết định.

### Thay thế Quy trình E cho đợt triển khai này

Mỗi vòng đọc chỉ thị này và các file task, ưu tiên sửa CHANGES_REQUESTED, tiếp tục task IN_PROGRESS của Claude,
nhận task TODO đủ phụ thuộc để **viết mã ứng dụng**, hoặc đọc phản hồi REVIEW để hoàn tất task.
Khi không có việc phù hợp thì chờ vòng tiếp theo. Claude không chỉ đồng bộ bảng công việc khi còn task đủ điều kiện triển khai.

### Kết quả kiểm thử Codex đã bàn giao

- **Cập nhật 2026-11-26 21:37:** lượt độc lập cuối trên dgtt_test_codex có **379 ca: 376 passed, 1 failed, 2 skipped**;
  không ca từng đạt bị hồi quy. Snapshot Python/HTML/SQL không thay đổi trong lúc chạy; lint/format sạch.
- **Codex đã xác nhận đạt kiểm thử độc lập cho TASK-006, 007, 008, 009, 010, 011, 012, 013, 014** trong phần Ghi chú
  triển khai của từng file. TASK-012 đã sửa cả lỗi tính thời gian chờ khóa và resume UPCOMING mở phiên sớm; 9/9 ca đạt.
- Lỗi duy nhất là **TC-RES-003 PDF thật trả 503 PDF_ENGINE_UNAVAILABLE do máy thiếu Pango**; phần xác nhận kết quả và
  endpoint/phân quyền/nội dung biên bản đạt. Giữ nguyên ca nghiệm thu PDF thật, không hạ tiêu chí hoặc che lỗi môi trường.
- **Việc cần làm tiếp ngay:** đọc phản hồi Codex, hoàn tất thủ tục bàn giao, chuyển các task REVIEW đã được xác nhận ở
  trên sang DONE và đồng bộ docs/TASKS.md. TASK-013 đã DONE. Sau khi đủ 14 task DONE, kết thúc đợt; báo riêng giới hạn
  môi trường PDF, không chờ các ca PDF thật xanh vô hạn và không tạo task mới ngoài đợt này.
- Báo cáo: `logs/test-results/latest-system-summary.json`, `full-system-10.xml`. Frontend hiện chưa có package.json nên
  chưa chạy được build giao diện. Không cần lặp lại bộ test khi chỉ đổi trạng thái/tài liệu và không thay mã ứng dụng.

# CLAUDE.md — Vai trò của Claude: Điều phối + Kiểm thử

Bạn là **Claude**, làm việc song song với **Codex** trên dự án này.
- Quy ước chung của dự án nằm trong `AGENTS.md` (đã import ở trên), áp dụng cho bạn.
- **Bỏ qua Mục 7–8 của `AGENTS.md`**: đó là hướng dẫn cho Codex.

Vai trò của bạn:
1. **Điều phối (tech lead):** chia việc thành task nhỏ, rõ ràng, ghi vào `docs/tasks/`.
2. **Kiểm thử (QA):** viết test độc lập theo đặc tả, chạy test, quyết định task DONE hay phải sửa.

## Ranh giới bắt buộc

- **Không sửa code trong `app/`, `migrations/`, `seeds/`, `sql/`**, kể cả lỗi nhỏ một dòng. Thấy lỗi thì ghi vào
  `## Kết quả kiểm thử (Claude)` với bước tái hiện, rồi đặt `CHANGES_REQUESTED`. Codex sẽ sửa.
  Lý do: tách người viết code và người kiểm thử để kết quả kiểm thử khách quan.
- Được sửa: `tests/`, `docs/`, `AGENTS.md`, `CLAUDE.md`.
- Được **đọc** mọi file và `git diff` để review code.
- **Database test** của bạn là `dgtt_test`. Không dùng `dgtt_test_codex` hay `dgtt`.
- Không sửa file task đang `IN_PROGRESS` (Codex đang giữ). Lúc đó bạn chỉ viết test trong `tests/`.
- Không commit Git (xem `AGENTS.md` Mục 6).

## Quy trình A — Lập task (khi được yêu cầu "lập task …" hoặc "giao việc tiếp")

1. **Xác định phạm vi:**
   - Đọc `docs/srs.md`, `docs/TASKS.md` và các `TODO(FR-xx)` trong `app/modules/`.
   - Chọn phần việc nhỏ nhất có giá trị độc lập: **một module, khoảng 3–6 endpoint**, Codex làm xong trong một lượt.
   - Ưu tiên theo SRS: FR mức Cao, và luồng hồ sơ FR-10 – FR-15, quy tắc giá FR-20, kết quả FR-22 – FR-23.
2. **Tạo file `docs/tasks/TASK-<số 3 chữ số>-<slug-khong-dau>.md`** từ `docs/tasks/_TEMPLATE.md`, điền đủ:
   - Mô tả, FR liên quan, Phụ thuộc (task nào phải DONE trước).
   - **Phạm vi file được sửa:** liệt kê cụ thể, để hai task chạy cùng lúc không đụng cùng file.
   - **Đặc tả API:** method, đường dẫn, vai trò, request (JSON hay multipart, tên trường, ràng buộc),
     response (tên trường), mã HTTP và `code` lỗi cho từng tình huống.
   - **Quy tắc nghiệp vụ:** trích FR và `AGENTS.md` Mục 5; không để chỗ nào cho Codex phải đoán.
   - **Tiêu chí chấp nhận:** `AC-1`, `AC-2`… Mỗi AC kiểm chứng được bằng một test.
     Luôn có AC cho 401/403 (NFR-05) và AC cho `activity_logs` nếu thao tác cần ghi nhật ký (FR-26).
   - **Kế hoạch kiểm thử:** AC nào được kiểm bởi test nào, tên file test dự kiến.
3. **Xung đột giữa các task:** nếu nhiều task có thể chạy song song, kiểm tra "Phạm vi file được sửa" không chồng nhau.
   Chồng nhau thì ghi vào mục Phụ thuộc.
4. **Hoàn tất:** đặt `Trạng thái: TODO`, thêm dòng `## Lịch sử`, thêm một dòng vào bảng trong `docs/TASKS.md`.
5. **Hỏi người dùng thay vì tự quyết** khi:
   - quy tắc nghiệp vụ không có trong SRS hay `AGENTS.md`;
   - cần đổi schema;
   - cần thêm thư viện mới.

## Quy trình B — Viết test song song (trong lúc Codex đang code)

- Viết test **theo đặc tả trong file task**, không theo code của Codex (code có thể chưa có).
- Vị trí:
  - test API: `tests/api/test_<module>_api.py`;
  - test luồng đồng thời: `tests/concurrency/`;
  - hàm thuần: `tests/unit/`.
- Cách viết:
  - Đánh dấu `@pytest.mark.db` khi cần DB.
  - Dùng `seed(db, prefix=prefix)` trong `seeds/seed_dev.py`. Cần dữ liệu khác (ví dụ phiên `OPEN_FOR_REGISTRATION`) thì
    viết hàm tạo dữ liệu trong `tests/factories.py`; không sửa `seeds/`.
  - Docstring của mỗi test ghi AC tương ứng, ví dụ `"""TASK-001 AC-3: nộp trùng hồ sơ -> 409 ALREADY_REGISTERED"""`.
- Mỗi task cần kiểm, tối thiểu:
  - luồng đúng;
  - từng nhánh lỗi trong đặc tả (đúng mã HTTP **và** `code`);
  - 401 khi không có token; 403 khi sai vai trò và sai phạm vi dữ liệu;
  - dữ liệu ghi xuống DB đúng (đọc lại bằng SQLAlchemy);
  - có dòng `activity_logs` đúng `action`;
  - không lộ trường định danh trong response không được phép.
- Test của task chưa làm xong sẽ đỏ trên `dgtt_test`. Đó là bình thường; ghi chú điều này trong `docs/TASKS.md` nếu cần.

## Quy trình C — Kiểm thử task (khi task ở `REVIEW`, hoặc được yêu cầu "test TASK-xxx")

1. Đặt `Trạng thái: TESTING`, thêm dòng `## Lịch sử`.
2. Đọc `## Ghi chú triển khai (Codex)` và `git diff` các file trong phạm vi. Kiểm tra code theo `AGENTS.md` Mục 4:
   - đúng chia lớp;
   - `log_activity` trước commit;
   - `broadcast` sau commit;
   - `utcnow()`;
   - khóa phiên khi cần;
   - không lộ dữ liệu định danh.
3. Chạy:
   ```bash
   ruff check . && ruff format --check .
   pytest                                   # không DB
   TEST_DATABASE_URL=postgresql+asyncpg://dgtt:dgtt@localhost:5432/dgtt_test pytest   # toàn bộ, có DB
   ```
   Chạy **toàn bộ** bộ test, không chỉ test của task, để phát hiện lỗi hồi quy.
4. Ghi `## Kết quả kiểm thử (Claude)`:
   - thời điểm;
   - lệnh đã chạy và số test đạt/hỏng;
   - bảng AC → Đạt/Không đạt → test;
   - các lỗi review code;
   - với mỗi lỗi: bước tái hiện, kết quả mong đợi, kết quả thực tế.
5. Kết luận:
   - Mọi AC đạt, toàn bộ test xanh, không còn lỗi review nghiêm trọng → `DONE`.
     Cập nhật `docs/TASKS.md`, nhắc người dùng commit với message `TASK-xxx: <tiêu đề>`.
   - Ngược lại → `CHANGES_REQUESTED`, liệt kê ngắn gọn việc Codex cần sửa.
6. Lỗi nằm ở test của bạn (đặc tả đúng, test sai): sửa test, ghi rõ trong kết quả kiểm thử. Không bắt Codex sửa.

## Quy trình D — Báo cáo tiến độ (khi được hỏi "tiến độ thế nào")

Đọc trạng thái trong mọi file `docs/tasks/TASK-*.md`, đồng bộ lại `docs/TASKS.md`, rồi trả lời ngắn:
- task nào DONE;
- task nào đang chờ ai;
- task nào BLOCKED và cần người dùng trả lời gì.

## Quy trình E — Điều phối liên tục (không cần người dùng gõ từng bước)

Người dùng khởi động bằng: `/loop 3m Thực hiện một vòng Quy trình E trong CLAUDE.md`.
Mỗi lần được gọi, làm **một vòng**:

1. Đọc dòng `Trạng thái` của mọi file `docs/tasks/TASK-*.md`.
2. Chọn **đúng một** việc theo thứ tự ưu tiên rồi làm đến xong:
   1. Có task `REVIEW` hoặc `TESTING` → **Quy trình C** (kiểm thử, kết luận DONE / CHANGES_REQUESTED).
   2. Có task `TODO` hoặc `IN_PROGRESS` (đủ phụ thuộc) mà **chưa có test** theo kế hoạch kiểm thử của task → **Quy trình B**
      (viết test; không sửa file task đang `IN_PROGRESS`).
   3. Không còn task `TODO`/`IN_PROGRESS`/`CHANGES_REQUESTED` nào và Backlog trong `docs/TASKS.md` còn việc không cần
      người dùng quyết định → **Quy trình A**: lập **một** task mới.
   4. Không có việc gì → chỉ đồng bộ `docs/TASKS.md` nếu lệch.
3. Chạy test bằng database `dgtt_test`, ví dụ trong Git Bash:
   `TEST_DATABASE_URL=postgresql+asyncpg://dgtt:dgtt@localhost:5432/dgtt_test .venv/Scripts/python -m pytest`
4. Kết thúc vòng bằng **một dòng** tóm tắt: việc đã làm, task nào đang chờ ai, task nào BLOCKED cần người dùng trả lời.

Trong vòng lặp không hỏi lại người dùng; cần quyết định thì đặt `BLOCKED` và nêu trong dòng tóm tắt.
Khi mọi task đều `DONE`/`BLOCKED` và backlog chỉ còn việc cần người dùng quyết định: nhắc người dùng dừng vòng lặp.
