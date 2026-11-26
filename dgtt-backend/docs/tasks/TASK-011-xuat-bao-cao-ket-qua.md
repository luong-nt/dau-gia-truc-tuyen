# TASK-011: Xuất báo cáo tổng hợp kết quả (CSV/PDF)

- **Trạng thái:** REVIEW
- **FR/NFR liên quan:** FR-25, NFR-05, NFR-08, FR-26
- **Module:** `app/modules/reports`
- **Phụ thuộc:** TASK-010 (chung file module `reports`, dùng chung quy ước khoảng thời gian), TASK-013
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

Quản trị viên và Nhân viên lọc các phiên đã kết thúc theo thời kỳ và xuất báo cáo tổng hợp kết quả dạng CSV hoặc PDF. Báo cáo ghi
thời điểm tạo và điều kiện lọc; **không cộng kết quả dự kiến (DRAFT) vào tổng giá trúng chính thức**.

## Phạm vi file được sửa (Codex)

- `app/modules/reports/router.py`
- `app/modules/reports/schemas.py`
- `app/modules/reports/service.py`
- `app/modules/reports/repository.py`
- `app/templates/report.html`

Chỉ **dùng**: `app/modules/reports/exporters.py` (`to_csv`, `render_pdf`, `render_html`), `app/core/money.py`.

## Đặc tả API

### `GET /api/v1/reports/results/export`

- **Vai trò:** ADMIN, STAFF. AUCTIONEER, BIDDER → 403 `FORBIDDEN`. Không token → 401.
- **Query:** `format` (bắt buộc, `csv` hoặc `pdf`), `from`, `to` (quy ước khoảng thời gian như TASK-010, lọc theo
  `auction_sessions.end_time`).
- **Dữ liệu:** các phiên `status = ENDED` có `end_time` trong khoảng, sắp `end_time` tăng dần rồi `session_id` tăng dần.
  Mỗi phiên một dòng:

| Cột | Giá trị |
|---|---|
| `Mã phiên` | `PDG-{session_id}` |
| `Mã tài sản` | `assets.asset_code` |
| `Tài sản` | `assets.name` |
| `Giá khởi điểm` | CSV: chuỗi chữ số (`format_money`) |
| `Thời điểm kết thúc` | `end_time` ISO 8601 |
| `Trạng thái kết quả` | có bản `CONFIRMED` có người trúng → `ĐÃ XÁC NHẬN`; bản `CONFIRMED` không thành → `KHÔNG THÀNH`; không có bản `CONFIRMED` → `CHỜ XÁC NHẬN` |
| `Phiên bản` | `version_no` của bản `CONFIRMED`; rỗng nếu `CHỜ XÁC NHẬN` |
| `Mã người trúng` | `bidder_alias` của bản `CONFIRMED`; rỗng nếu không thành hoặc chờ xác nhận |
| `Giá trúng` | giá trúng của bản `CONFIRMED`; rỗng nếu không thành hoặc **chờ xác nhận (kể cả khi bản DRAFT có người trúng)** |

  **Tổng giá trúng chính thức** = tổng cột `Giá trúng`.

- **CSV** (`exporters.to_csv`, UTF-8 có BOM): đúng cấu trúc từng dòng sau:
  1. `Báo cáo tổng hợp kết quả đấu giá`
  2. `Thời điểm tạo`, `<utcnow() ISO 8601>`
  3. `Điều kiện lọc`, `from=<giá trị from hoặc "không giới hạn">; to=<giá trị to hoặc "không giới hạn">` (giá trị viết đúng
     chuỗi ISO đã nhận, ví dụ `2002-05-06T07:08:00`)
  4. dòng trống
  5. tiêu đề 9 cột theo đúng thứ tự bảng trên
  6. các dòng dữ liệu
  7. dòng trống
  8. `Tổng giá trúng chính thức`, `<tổng dạng chữ số>`

  Gợi ý: `to_csv` nhận `headers` là dòng 1 và `rows` là các dòng 2–8 (dòng trống = `[]`).
- **PDF:** gọi `exporters.render_pdf("report.html", context)` qua thuộc tính module (như TASK-004/006). HTML phải có:
  tiêu đề, thời điểm tạo, điều kiện lọc, mọi `Mã phiên`, nhãn trạng thái kết quả, giá dạng `105.000.000`
  (`format_vnd`), tổng giá trúng chính thức dạng `310.000.000`.
  Thiếu WeasyPrint (`OSError`/`ImportError`) → 503 `PDF_ENGINE_UNAVAILABLE`, không ghi log.
- **Response 200:** `Content-Type` `text/csv` (có thể kèm `; charset=utf-8`) hoặc `application/pdf`;
  `Content-Disposition: attachment; filename="bao-cao-ket-qua-<YYYYMMDDHHMMSS>.<csv|pdf>"`.
- **Lỗi:** thiếu/sai `format` → 422 `VALIDATION_ERROR`; `from ≥ to` → 422 `INVALID_DATE_RANGE`.
- **Nhật ký:** sau khi xuất thành công: `log_activity(action="EXPORT_RESULTS_REPORT", entity_type="report", entity_id=None,
  user_id=người xuất, new_value=format, reason=<chuỗi điều kiện lọc như dòng 3 CSV>)` rồi `commit`.

## Tiêu chí chấp nhận

- **AC-1:** Không token → 401; AUCTIONEER, BIDDER → 403; ADMIN, STAFF → 200.
- **AC-2:** CSV đúng cấu trúc 8 phần, đúng tiêu đề cột, dòng dữ liệu đúng thứ tự và giá trị cho các trường hợp: có người trúng,
  không thành, chờ xác nhận (DRAFT có người trúng nhưng `Giá trúng` rỗng), chưa có kết quả, đã điều chỉnh (dùng bản `CONFIRMED`).
- **AC-3:** Chỉ phiên `ENDED` có `end_time` trong `[from, to)`; phiên `CANCELLED` hoặc `end_time = to` không có trong báo cáo.
- **AC-4:** Tổng giá trúng chính thức chỉ cộng bản `CONFIRMED`.
- **AC-5:** Dòng 2–3 ghi thời điểm tạo và điều kiện lọc; không gửi `from`/`to` → `không giới hạn`.
- **AC-6:** PDF: HTML có các nội dung nêu ở đặc tả; header `application/pdf`, tên tệp `.pdf`.
- **AC-7:** Ghi log `EXPORT_RESULTS_REPORT` đúng người, `new_value`; PDF lỗi 503 không ghi log.
- **AC-8:** `format` thiếu/sai → 422 `VALIDATION_ERROR`; `from ≥ to` → 422 `INVALID_DATE_RANGE`.

## Kế hoạch kiểm thử (Claude)

| AC | Test | File |
|---|---|---|
| AC-1 | `test_export_report_auth` | `tests/api/test_report_export_api.py` |
| AC-2, AC-3, AC-4, AC-5 | `test_export_report_csv` | `tests/api/test_report_export_api.py` |
| AC-5 | `test_export_report_csv_unbounded_filter` | `tests/api/test_report_export_api.py` |
| AC-6 | `test_export_report_pdf` | `tests/api/test_report_export_api.py` |
| AC-7 | `test_export_report_log`, `test_export_report_pdf_engine_unavailable` | `tests/api/test_report_export_api.py` |
| AC-8 | `test_export_report_validation` | `tests/api/test_report_export_api.py` |

## Ghi chú triển khai (Codex)

**KẾT LUẬN HIỆN TẠI CỦA CODEX: CHẤP THUẬN HOÀN TẤT, không còn chờ Codex.** 9/9 ca xuất báo cáo đạt,
lượt cuối full-system-10.xml không hồi quy. PDF thật vẫn cần Pango như giới hạn môi trường đã nêu;
Claude cập nhật DONE phần triển khai theo phản hồi kiểm thử độc lập bên dưới, không hạ tiêu chí test PDF thật.

**Người triển khai: Claude** (theo chỉ thị người dùng 2026-11-26 trong `CLAUDE.md`; Codex kiểm thử độc lập).

- **File đã sửa:** `app/modules/reports/router.py` (`GET /reports/results/export`), `service.py` (`export_results`,
  `describe_filters`, `_report_rows`), `repository.py` (`list_ended_sessions_for_report`), `app/templates/report.html`.
- **Mã lỗi:** `VALIDATION_ERROR` (format thiếu/sai), `INVALID_DATE_RANGE`, `PDF_ENGINE_UNAVAILABLE` (503), 401/403.
- **Ghi chú:** CSV qua `exporters.to_csv` (BOM UTF-8) đúng 8 phần; tiền CSV dạng chữ số (`format_money`), PDF dạng
  `105.000.000` (`format_vnd`). Chỉ bản `CONFIRMED` có người trúng được cộng vào tổng; DRAFT không hiện giá trúng.
  Log `EXPORT_RESULTS_REPORT` (`entity_type="report"`, `new_value=format`, `reason=điều kiện lọc`) sau khi xuất thành công.
  Response giữ header `X-Access-Token` (NFR-04). Tên tệp `bao-cao-ket-qua-<YYYYMMDDHHMMSS>.<csv|pdf>`.
- **Sửa test của Claude:** `test_export_report_pdf` và `test_export_report_csv` dùng chung cửa sổ thời gian nên tổng bị cộng
  dữ liệu của nhau (620tr thay vì 310tr) → tách cửa sổ riêng `T2` cho test PDF. Lỗi ở test, không phải mã ứng dụng.
- **Khác đặc tả:** không.
- **Tự kiểm tra (2026-11-26 23:20):** ruff sạch. `tests/api/test_report_export_api.py` 10/10 (gồm 2 ca 503).
  `dgtt_test` toàn bộ: **367 passed, 2 skipped, 1 failed** (chỉ TC-RES-003 — thiếu Pango). Không hồi quy.

### Phản hồi kiểm thử độc lập mã hiện có — Codex, 2026-11-26 21:10

- `logs/test-results/full-system-09.xml` trên dgtt_test_codex: **367 passed, 1 failed, 2 skipped**; **9/9 ca xuất báo cáo
  đạt**, không ca từng đạt bị hồi quy. Ruff check/format sạch.
- Review: chỉ ADMIN/STAFF, lọc phiên ENDED theo end_time, chỉ cộng bản CONFIRMED; CSV UTF-8 BOM và điều kiện lọc đúng,
  PDF đi qua module exporters và kiểm HTML thật bằng test; log sau khi tạo nội dung thành công, không log khi PDF 503.
  Response xuất giữ X-Access-Token. PDF thật vẫn cần Pango, giữ nguyên giới hạn môi trường thay vì hạ tiêu chí test.
- **Mã TASK-011 hiện tại đạt kiểm thử độc lập**, có thể hoàn tất sau khi Claude ghi xong bàn giao nếu không thay đổi mã tiếp.
  Lỗi duy nhất toàn hệ thống là TC-RES-003 PDF thật thiếu Pango; chưa thể nghiệm thu PDF thật trên máy này.

## Kết quả kiểm thử (Claude)

_(Claude điền khi kiểm thử.)_

## Quyết định của người dùng

_(Không có.)_

## Lịch sử

- 2026-11-26 11:00 | Claude | TODO | Tạo task
- 2026-11-26 22:55 | Claude | IN_PROGRESS | Claude triển khai (mã TASK-010 đã có)
- 2026-11-26 23:20 | Claude | REVIEW | Bàn giao, chờ Codex kiểm thử độc lập
