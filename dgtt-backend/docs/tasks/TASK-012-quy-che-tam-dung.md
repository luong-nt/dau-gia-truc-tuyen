# TASK-012: Quy chế tạm dừng phiên: có kéo dài `end_time` không

- **Trạng thái:** DONE
- **FR/NFR liên quan:** FR-17 (tạm dừng và tiếp tục theo quy chế), FR-19 (đồng hồ theo `end_time` máy chủ), FR-26
- **Module:** `app/modules/sessions`, `app/jobs/session_jobs.py`
- **Phụ thuộc:** Không (người dùng đã chọn A)
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

Hiện tại (`sessions.service.resume_session`): tạm dừng **không** kéo dài `end_time`. Nếu tạm dừng đến quá `end_time` thì không
tiếp tục được nữa (`BusinessRuleError`). Job tự đóng chỉ quét phiên `IN_PROGRESS`, nên phiên `PAUSED` quá `end_time` nằm yên ở
`PAUSED` cho đến khi đấu giá viên đóng phiên. SRS và AGENTS.md chưa quy định, nên cần người dùng quyết định trước khi giao Codex.

## Câu hỏi cho người dùng

1. **Khi tiếp tục phiên sau tạm dừng, có kéo dài `end_time` không?**
   - **(A) Có, cộng đúng thời gian đã tạm dừng** (đề xuất): `end_time_mới = end_time_cũ + (thời điểm tiếp tục − thời điểm tạm dừng)`.
     Người tham gia không mất thời gian trả giá vì sự cố. Ghi `activity_logs` `field_name="end_time"` và broadcast sự kiện có
     `end_time` mới để đồng hồ các bên cập nhật (FR-19).
   - **(B) Không** (giữ như hiện tại): tạm dừng vẫn tính vào thời lượng phiên.
   - **(C) Đấu giá viên nhập `end_time` mới khi tiếp tục** (bắt buộc ≥ thời điểm hiện tại + N phút).
2. **Phiên `PAUSED` đã quá `end_time`** (chỉ áp dụng khi chọn B): hệ thống tự đóng như phiên `IN_PROGRESS`, hay chờ đấu giá viên
   đóng thủ công (như hiện tại)?

Sau khi có câu trả lời, Claude viết đặc tả API, tiêu chí chấp nhận và test, rồi chuyển task sang `TODO`.

## Đặc tả (theo quyết định A của người dùng)

### Phạm vi file được sửa

- `app/modules/sessions/service.py` (`resume_session`)
- `app/modules/sessions/repository.py` (truy vấn thời điểm tạm dừng gần nhất)

Không đổi schema. Thời điểm tạm dừng lấy từ `activity_logs.created_at` của dòng `PAUSE_SESSION` **mới nhất** của phiên
(kết nối DB đặt `timezone=UTC` trong `app/db/session.py`, nên cùng mốc với `utcnow()`).

### `POST /api/v1/sessions/{session_id}/resume` (đã có, đổi hành vi)

Vai trò, request (`reason` tuỳ chọn), quyền và mã lỗi giữ nguyên. Khi chuyển `PAUSED` → `IN_PROGRESS` thành công:

1. `paused_at` = `created_at` của log `PAUSE_SESSION` mới nhất của phiên; `pause_duration = utcnow() − paused_at`
   (không âm; không tìm thấy log thì 0).
2. `end_time_mới = end_time_cũ + pause_duration`. Mỗi lần tạm dừng/tiếp tục cộng bù riêng (nhiều lần thì cộng dồn).
3. Bỏ chặn "đã quá giờ kết thúc" theo `end_time` **cũ**; chỉ chặn (422 `BUSINESS_RULE_VIOLATION` như hiện tại) nếu
   `utcnow() ≥ end_time_mới`.
4. Nhật ký, trước `commit`, cùng transaction, `user_id` = đấu giá viên:
   - `RESUME_SESSION` như hiện tại;
   - thêm `EXTEND_END_TIME`, `entity_type="auction_session"`, `field_name="end_time"`, `old_value`/`new_value` là
     `end_time` cũ/mới (ISO 8601), `reason = "Bù thời gian tạm dừng <số giây làm tròn> giây"`.
     Không ghi dòng này khi `pause_duration = 0`.
5. Sự kiện realtime `status_changed` (sau commit) mang `end_time` **mới** để đồng hồ các bên cập nhật (FR-19).
   `GET /sessions/{id}` và `GET /sessions/{id}/state` trả `end_time` mới.
6. Phiên `PAUSED` quá `end_time` không bị scheduler tự đóng (giữ nguyên hành vi job, câu hỏi 2 không áp dụng cho A).

### Tiêu chí chấp nhận

- **AC-1:** Tạm dừng 10 phút rồi tiếp tục → `end_time` tăng ≈ 10 phút (sai số ≤ 5 giây); response, `GET /sessions/{id}` và
  `/state` trả `end_time` mới.
- **AC-2:** Có `RESUME_SESSION` và `EXTEND_END_TIME` (`field_name="end_time"`, old/new đúng, `reason` có số giây).
- **AC-3:** Tạm dừng trước `end_time` cũ và tiếp tục **sau** `end_time` cũ → vẫn tiếp tục được (200, `IN_PROGRESS`),
  `end_time` mới ở tương lai.
- **AC-4:** Hai lần tạm dừng (5 phút và 3 phút) → `end_time` tăng tổng ≈ 8 phút; hai dòng `EXTEND_END_TIME`.
- **AC-5:** Quyền và lỗi giữ nguyên: đấu giá viên khác → 403; phiên không `PAUSED` → 422 `INVALID_STATUS_TRANSITION`;
  không đổi `end_time`.

### Kế hoạch kiểm thử (Claude)

| AC | Test | File |
|---|---|---|
| AC-1, AC-2 | `test_resume_extends_end_time` | `tests/api/test_session_pause_api.py` |
| AC-3 | `test_resume_after_old_end_time` | `tests/api/test_session_pause_api.py` |
| AC-4 | `test_multiple_pauses_accumulate` | `tests/api/test_session_pause_api.py` |
| AC-5 | `test_resume_errors_keep_end_time` | `tests/api/test_session_pause_api.py` |

## Ghi chú triển khai (Codex)

**Người triển khai: Claude** (theo chỉ thị người dùng 2026-11-26 trong `CLAUDE.md`; Codex kiểm thử độc lập).

- **File đã sửa:** `app/modules/sessions/service.py` (`resume_session`), `app/modules/sessions/repository.py`
  (`get_last_pause_time`: `created_at` của log `PAUSE_SESSION` mới nhất).
- **Hành vi:** kiểm tra chuyển trạng thái trước (giữ 422 `INVALID_STATUS_TRANSITION`), rồi tính
  `pause_duration = utcnow() − paused_at` (không âm), `end_time_mới = end_time_cũ + pause_duration`; chỉ chặn khi
  `utcnow() ≥ end_time_mới`. Ghi `EXTEND_END_TIME` (old/new ISO, `reason` có số giây) khi `pause_duration > 0`, rồi
  `_apply` ghi `RESUME_SESSION`, commit, phát `status_changed` có `end_time` mới (FR-19).
- Job tự đóng không đổi (chỉ quét `IN_PROGRESS`). Không đổi schema.
- **Khác đặc tả:** không.
- **Tự kiểm tra (2026-11-26 23:35):** ruff sạch. `tests/api/test_session_pause_api.py` 4/4; bidding + sessions vẫn đạt.
  `dgtt_test` toàn bộ: **371 passed, 2 skipped, 1 failed** (chỉ TC-RES-003 — PDF 503 thiếu Pango, lỗi môi trường).

### Phản hồi độc lập sớm — Codex: mốc tạm dừng đang tính cả thời gian chờ khóa

- Tái hiện trên dgtt_test_codex, database/API thật: transaction khác giữ khóa dòng phiên 8 giây; gọi POST pause của đấu giá
  viên hợp lệ và đợi nó thử lấy khóa; sau 8 giây nhả khóa, pause thành công; chờ 0,2 giây rồi POST resume.
  Chỉ điều phối lịch chạy bằng wrapper cho get_session_for_update để biết request đã tới bước lấy khóa, không giả dữ liệu
  trả về của DB/API.
- **Thực tế:** end_time được cộng **8,304 giây**, trong khi khoảng tạm dừng thực tế (kể từ lúc nhả khóa tới khi resume xong)
  không quá **0,344 giây**. Bị cộng thừa **7,960 giây** chờ khóa, sai quyết định A "cộng bù đúng thời gian đã tạm dừng".
- Nguyên nhân: ActivityLog.created_at mặc định CURRENT_TIMESTAMP/NOW() là **thời điểm bắt đầu transaction** PostgreSQL,
  không phải thời điểm chuyển PAUSED sau khi lấy được khóa. Transaction đã bắt đầu từ truy vấn xác thực trước khi chờ khóa.
- **Cần sửa trước khi hoàn tất:** dùng/ghi mốc UTC thực tế khi chuyển sang PAUSED dưới khóa, giữ schema và nguyên tắc audit
  chỉ ghi thêm; ghi rõ phạm vi bổ sung nếu cần. Bổ sung test hồi quy có chờ khóa để không cộng bù thời gian phiên vẫn còn
  IN_PROGRESS. Các ca chỉ lùi created_at của log trong test hiện tại chưa bắt được lỗi này.

- **Yêu cầu sửa 1 sau bàn giao:** bản REVIEW vẫn dùng DEFAULT CURRENT_TIMESTAMP của ActivityLog cho PAUSE_SESSION,
  chưa có test chờ khóa và vẫn cộng thừa thời gian như số liệu trên. Chuyển CHANGES_REQUESTED; cần sửa mốc thời gian
  và bổ sung hồi quy trước khi hoàn tất. Có thể thêm tùy chọn timestamp tương thích ngược cho helper audit nếu cần,
  mặc định giữ hành vi các caller khác; ghi lý do và phạm vi bổ sung trong task, không đổi schema.

### Lần sửa 1 (Claude, 2026-11-26 23:55) — theo yêu cầu sửa 1 của Codex (mốc tạm dừng tính cả thời gian chờ khoá)

- **Nguyên nhân:** log `PAUSE_SESSION` dùng `DEFAULT CURRENT_TIMESTAMP` = thời điểm **bắt đầu transaction** (lúc xác thực),
  sớm hơn lúc lấy được khoá phiên nếu phải chờ.
- **Sửa:**
  - `app/core/audit.py` (**ngoài phạm vi ban đầu**, theo gợi ý của Codex): `log_activity` thêm tham số tuỳ chọn
    `created_at`; không truyền thì giữ nguyên hành vi (DB tự đặt) cho mọi caller khác. Không đổi schema, vẫn chỉ ghi thêm.
  - `app/modules/sessions/service.py`: `_apply` nhận `logged_at`; `pause_session` truyền `utcnow()` **sau khi** đã khoá dòng
    phiên, nên mốc tạm dừng = thời điểm thực tế chuyển sang `PAUSED`. `resume_session` giữ nguyên cách đọc mốc này.
- **Test hồi quy:** `tests/api/test_session_pause_api.py::test_pause_time_excludes_lock_wait` — transaction khác giữ
  `FOR UPDATE` dòng phiên 2 giây khi lệnh pause đang chờ; resume ngay sau đó phải cộng bù < 1 giây.
  Đã xác minh: tắt bản sửa (`logged_at=None`) thì test **đỏ**; bật lại thì xanh.
- **Kết quả:** `test_session_pause_api.py` 5/5. `dgtt_test` toàn bộ: **372 passed, 2 skipped, 1 failed** (chỉ TC-RES-003 —
  PDF 503 thiếu Pango, lỗi môi trường). Ruff sạch.

### Kiểm tra lại và yêu cầu sửa 2 — Codex

- Lỗi mốc thời gian sau chờ khóa **đã được sửa**: chạy lại kịch bản giữ khóa 8 giây, chỉ cộng **0,265 giây**, trong khi
  khoảng thực sự tạm dừng không quá **0,314 giây**. Không còn cộng thời gian chờ khóa; kiểm tra độc lập đạt.
- **Phát hiện lỗi AC-5:** tạo phiên UPCOMING có start_time còn ở tương lai (3 ngày), đấu giá viên được phân công gọi
  POST `/api/v1/sessions/{id}/resume` với `{}` → **200, IN_PROGRESS**, tức mở phiên sớm bằng endpoint tiếp tục.
  Mong đợi **422 INVALID_STATUS_TRANSITION**, trạng thái và end_time không đổi: resume chỉ được dùng khi PAUSED.
- Nguyên nhân: ensure_transition(UPCOMING, IN_PROGRESS) là chuyển hợp lệ cho thao tác OPEN, nên kiểm máy trạng thái chung
  không đủ để bảo vệ endpoint RESUME. Cần kiểm tra rõ trạng thái nguồn PAUSED và bổ sung test UPCOMING (cùng các trạng thái
  không PAUSED phù hợp) để không mở phiên trước giờ. Đây là yêu cầu AC-5 đã có, không phải thay đổi quyết định nghiệp vụ A.
- Chưa đủ điều kiện hoàn tất TASK-012 cho đến khi sửa và kiểm tra lại trường hợp này.

### Lần sửa 2 (Claude, 2026-11-27 00:10) — theo yêu cầu sửa AC-5 của Codex (resume UPCOMING mở phiên sớm)

- **Nguyên nhân:** `ensure_transition(UPCOMING, IN_PROGRESS)` hợp lệ vì đó là chuyển của thao tác MỞ phiên, nên RESUME đi
  qua được mà không kiểm giờ bắt đầu. Lỗi có từ trước task này nhưng thuộc AC-5.
- **Sửa:** `sessions/service.py::resume_session` kiểm tra rõ `session.status == PAUSED` (sau kiểm quyền), khác thì 422
  `INVALID_STATUS_TRANSITION`, không đổi trạng thái/`end_time`, không ghi log.
- **Test hồi quy:** `test_resume_requires_paused` tham số hoá `UPCOMING`, `OPEN_FOR_REGISTRATION`, `DRAFT`, `ENDED`
  (kiểm cả trạng thái, `end_time` và không có log `RESUME_SESSION`).
- **Kết quả:** `test_session_pause_api.py` 9/9; bidding + sessions đạt. `dgtt_test` toàn bộ: **376 passed, 2 skipped,
  1 failed** (chỉ TC-RES-003 — PDF 503 thiếu Pango, lỗi môi trường). Ruff sạch.

### Kiểm thử độc lập sau hai lần sửa — Codex, 2026-11-26 21:37

- Lượt đầy đủ `logs/test-results/full-system-10.xml` trên dgtt_test_codex: **379 ca, 376 passed, 1 failed, 2 skipped**.
  **9/9 ca TASK-012 đạt**, không ca từng đạt bị hồi quy. Snapshot Python/HTML/SQL không thay đổi trong lúc chạy.
- Kiểm tra riêng với khóa thật giữ 8 giây: cộng bù 0,265 giây, thời gian tạm dừng thực tế không quá 0,314 giây;
  không còn cộng cả thời gian chờ khóa. Helper audit chỉ thêm timestamp tuỳ chọn, mặc định giữ nguyên caller khác.
- Kiểm tra riêng UPCOMING: đã qua hạn nhận hồ sơ nhưng chưa tới giờ bắt đầu, gọi resume trả **422 INVALID_STATUS_TRANSITION**;
  trạng thái UPCOMING và end_time giữ nguyên. Lỗi yêu cầu sửa 2 đã được khắc phục.
- Review: khóa phiên trước khi tính bù, lấy mốc pause mới nhất, ghi EXTEND_END_TIME trước commit, broadcast end_time mới sau
  commit; scheduler không tự đóng PAUSED theo phương án A. Ruff check/format sạch.
- **TASK-012 đạt kiểm thử độc lập, đủ điều kiện hoàn tất theo phương án A người dùng đã chọn.**
  Lỗi duy nhất toàn hệ thống là TC-RES-003 PDF thật trả 503 PDF_ENGINE_UNAVAILABLE vì thiếu Pango, không thuộc TASK-012;
  ca nghiệm thu PDF vẫn giữ nguyên tiêu chí, không đổi thành pass/skip để che lỗi môi trường.

## Kết quả kiểm thử (Claude)

- **Claude tự kiểm (2026-11-27 00:10):** ruff sạch; `test_session_pause_api.py` 9/9; `dgtt_test` toàn bộ 376 passed,
  2 skipped, 1 failed (TC-RES-003, PDF thiếu Pango — lỗi môi trường, không thuộc task này).
- **Codex kiểm thử độc lập (Lịch sử 21:37):** 9/9 ca TASK-012 đạt sau hai lần sửa; toàn hệ thống 376 passed, 1 failed (PDF môi
  trường), 2 skipped; không hồi quy.

| AC | Kết quả | Test |
|---|---|---|
| AC-1 | Đạt | `test_resume_extends_end_time` |
| AC-2 | Đạt | `test_resume_extends_end_time` |
| AC-3 | Đạt | `test_resume_after_old_end_time` |
| AC-4 | Đạt | `test_multiple_pauses_accumulate` |
| AC-5 | Đạt | `test_resume_errors_keep_end_time`, `test_resume_requires_paused` |
| Hồi quy chờ khoá | Đạt | `test_pause_time_excludes_lock_wait` |

**Kết luận:** DONE.

## Quyết định của người dùng

- **2026-11-26 21:04 (giờ Việt Nam), người dùng chọn:** "A — Cộng bù đúng thời gian đã tạm dừng (đề xuất trong task)".
- Quy chế đã chốt: `end_time_mới = end_time_cũ + (thời điểm tiếp tục − thời điểm tạm dừng)`.
  Ghi nhật ký thay đổi end_time và phát sự kiện có end_time mới như phương án A đã mô tả.
- Claude nhận hoàn thiện đặc tả API, phạm vi sửa, AC và test theo A; sau đó chuyển TODO và triển khai theo phân công mới
  trong CLAUDE.md. Không còn chờ người dùng chọn A/B/C; câu hỏi 2 chỉ dành cho B nên không áp dụng.

## Lịch sử

- 2026-11-26 11:10 | Claude | BLOCKED | Tạo task, chờ người dùng chọn quy chế tạm dừng

- 2026-11-26 21:04 | Codex | BLOCKED | Ghi nhận quyết định trực tiếp của người dùng chọn A; bàn giao Claude hoàn thiện đặc tả/test và chuyển TODO.
- 2026-11-26 23:10 | Claude | TODO | Viết đặc tả, AC, test theo quyết định A của người dùng
- 2026-11-26 23:15 | Claude | IN_PROGRESS | Claude triển khai theo quyết định A
- 2026-11-26 23:35 | Claude | REVIEW | Bàn giao, chờ Codex kiểm thử độc lập

- 2026-11-26 21:17 | Codex | CHANGES_REQUESTED | Cộng thừa khoảng 8 giây chờ khóa vào thời gian tạm dừng; cần mốc UTC thực tế sau khóa và test hồi quy.
- 2026-11-26 23:55 | Claude | REVIEW | Lần sửa 1: mốc tạm dừng = utcnow() sau khi có khoá; test hồi quy chờ khoá

- 2026-11-26 21:27 | Codex | CHANGES_REQUESTED | Lỗi chờ khóa đã hết; còn AC-5: resume UPCOMING trả 200 và mở phiên sớm, cần chặn rõ trạng thái nguồn PAUSED.
- 2026-11-27 00:10 | Claude | REVIEW | Lần sửa 2: resume chỉ nhận phiên PAUSED + test hồi quy

- 2026-11-26 21:37 | Codex | REVIEW | Kiểm thử độc lập 9/9 ca TASK-012 đạt sau hai lần sửa; toàn bộ 376 passed/1 PDF-env failed/2 skipped, không hồi quy; đủ điều kiện DONE.
- 2026-11-27 00:25 | Claude | DONE | Đọc phản hồi Codex (9/9 đạt, không hồi quy); mọi AC đạt
