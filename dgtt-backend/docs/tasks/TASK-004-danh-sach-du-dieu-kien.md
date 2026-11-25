# TASK-004: Danh sách người đủ điều kiện và xuất CSV/PDF

- **Trạng thái:** DONE
- **FR/NFR liên quan:** FR-14, FR-15 (phần xuất danh sách), NFR-05, NFR-08, FR-26
- **Module:** `app/modules/registrations`
- **Phụ thuộc:** TASK-002 (DONE)
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

Nhân viên và đấu giá viên phụ trách phiên tra cứu danh sách người đủ điều kiện của một phiên (hồ sơ `APPROVED`),
sắp theo mã tham gia `NTG-01`, `NTG-02`… và xuất danh sách ra CSV hoặc PDF để in. Danh sách chỉ đọc: không có API
thêm/sửa/xoá người trong danh sách (FR-14: không thêm người chưa được duyệt bằng sửa thủ công). Số giấy tờ định danh chỉ
xuất khi người xuất chủ động yêu cầu; địa chỉ, số điện thoại **không bao giờ** xuất (FR-15).

Ngoài phạm vi: kiểm tra quyền vào phòng/gửi giá theo danh sách (đã có trong module `bidding`).

## Phạm vi file được sửa (Codex)

- `app/modules/registrations/router.py`
- `app/modules/registrations/schemas.py`
- `app/modules/registrations/service.py`
- `app/modules/registrations/repository.py`
- `app/modules/registrations/permissions.py`

Chỉ **dùng** (không sửa): `app/modules/reports/exporters.py` (`to_csv`, `render_pdf`), `app/templates/eligible_list.html`,
`app/modules/sessions/permissions.py`, `app/modules/sessions/repository.py`.

## Đặc tả API

### 1. `GET /api/v1/sessions/{session_id}/eligible-bidders`

- **Vai trò:** STAFF, hoặc AUCTIONEER **được phân công** phiên này
- **Response 200:** `EligibleListOut` (không phân trang, trả toàn bộ)

```json
{
  "session_id": 3, "session_code": "PDG-3", "asset_name": "Xe ô tô Toyota Vios 2020", "total": 2,
  "items": [
    {"registration_id": 11, "bidder_alias": "NTG-01", "full_name": "Nguyễn Văn A", "approved_at": "2026-11-25T14:00:00"},
    {"registration_id": 12, "bidder_alias": "NTG-02", "full_name": "Trần Thị B", "approved_at": null}
  ]
}
```

  - `full_name` = `registrations.submitted_full_name`.
  - `approved_at` = `reviewed_at` của dòng `registration_reviews` loại `APPROVE` **mới nhất** của hồ sơ; `null` nếu không có
    (dữ liệu mẫu cũ duyệt thẳng trong DB).
  - **Không có** trong item: `submitted_id_number`, `submitted_address`, `submitted_phone`, `bidder_id`.
- **Lỗi:**

| Tình huống | HTTP | `code` |
|---|---|---|
| Chưa đăng nhập | 401 | `UNAUTHORIZED` |
| BIDDER, ADMIN, hoặc AUCTIONEER không được phân công phiên này | 403 | `FORBIDDEN` |
| Phiên không tồn tại | 404 | `NOT_FOUND` |

### 2. `GET /api/v1/sessions/{session_id}/eligible-bidders/export`

- **Vai trò:** như mục 1
- **Query:**

| Tham số | Bắt buộc | Giá trị |
|---|---|---|
| `format` | Có | `csv` \| `pdf` |
| `include_identity` | Không | `true` \| `false`, mặc định `false` |

- **Response 200 khi `format=csv`:**
  - `Content-Type: text/csv; charset=utf-8`
  - `Content-Disposition: attachment; filename="danh-sach-du-dieu-kien-PDG-<session_id>.csv"`
  - Nội dung: `exporters.to_csv(...)` (UTF-8 có BOM). Dòng tiêu đề **đúng thứ tự**:
    `STT`, `Mã tham gia`, `Họ tên`, và thêm `Số giấy tờ` ở cuối **chỉ khi** `include_identity=true`.
    Mỗi dòng tiếp theo: số thứ tự từ 1, `bidder_alias`, `submitted_full_name`, (`submitted_id_number`).
    Thứ tự dòng như mục 1.
- **Response 200 khi `format=pdf`:**
  - `Content-Type: application/pdf`
  - `Content-Disposition: attachment; filename="danh-sach-du-dieu-kien-PDG-<session_id>.pdf"`
  - Nội dung: `exporters.render_pdf("eligible_list.html", context)`, **gọi qua module** (`from app.modules.reports import
    exporters` rồi `exporters.render_pdf(...)`, không `from ... import render_pdf`) để test thay thế được. `context`:

| Khoá | Giá trị |
|---|---|
| `session_code` | `PDG-<id>` |
| `asset_name` | tên tài sản |
| `rows` | danh sách dict `{"bidder_alias", "full_name", "id_number"}`; `id_number` = `None` khi không `include_identity` |
| `include_identity` | `bool` |
| `generated_at` | `utcnow()` định dạng `"%d/%m/%Y %H:%M"` (UTC) |
| `generated_by` | `full_name` của người xuất |

- **Lỗi:** như mục 1, cộng thêm:

| Tình huống | HTTP | `code` |
|---|---|---|
| Thiếu `format` hoặc giá trị khác `csv`/`pdf`; `include_identity` không phải boolean | 422 | `VALIDATION_ERROR` |
| `render_pdf` ném `OSError` hoặc `ImportError` (máy chủ thiếu thư viện hệ thống của WeasyPrint, ví dụ Windows không có Pango) | 503 | `PDF_ENGINE_UNAVAILABLE` |

  Lỗi 503: ném `AppError("…", code="PDF_ENGINE_UNAVAILABLE", status_code=503)` từ `app/core/exceptions.py`, message tiếng
  Việt gợi ý xuất CSV hoặc chạy bằng Docker. **Không** ghi `activity_logs` khi xuất thất bại.

## Quy tắc nghiệp vụ

1. Danh sách = các hồ sơ của phiên có `status = APPROVED` (luôn có `bidder_alias`). Hồ sơ `PENDING`, `NEEDS_SUPPLEMENT`,
   `REJECTED` không bao giờ xuất hiện.
2. **Thứ tự:** theo số trong `bidder_alias` tăng dần (so sánh **số**, `NTG-02` trước `NTG-10`; không sắp chuỗi thuần).
3. **Quyền** (thêm hàm vào `registrations/permissions.py`, dùng lại `sessions.permissions.is_assigned_auctioneer`):
   STAFF xem/xuất được mọi phiên; AUCTIONEER chỉ phiên mình được phân công; ADMIN và BIDDER → 403
   (FR-14/FR-15 chỉ nêu Nhân viên và Đấu giá viên).
   Kiểm tra theo thứ tự: phiên tồn tại (404) → quyền phạm vi (403).
4. Xem được ở **mọi** trạng thái phiên (kể cả sau khi phiên kết thúc, để đối chiếu).
5. **Dữ liệu định danh:** API danh sách (mục 1) không bao giờ trả số giấy tờ. Khi xuất, số giấy tờ chỉ có khi
   `include_identity=true`. Địa chỉ và số điện thoại không xuất trong mọi trường hợp.
6. **Nhật ký (FR-26):** mỗi lần **xuất thành công** ghi một dòng `activity_logs`: `action = "EXPORT_ELIGIBLE_LIST"`,
   `entity_type = "auction_session"`, `entity_id = session_id`, `user_id` = người xuất,
   `new_value` = `"csv"` / `"pdf"`, thêm hậu tố `"+identity"` khi `include_identity=true` (ví dụ `"csv+identity"`).
   Xem danh sách (mục 1) không ghi nhật ký. Ghi log và `commit` **sau khi** đã tạo xong nội dung tệp.

## Tiêu chí chấp nhận

- **AC-1:** STAFF xem danh sách của phiên có hồ sơ ở đủ 4 trạng thái → chỉ hồ sơ `APPROVED`; đúng `session_code`,
  `asset_name`, `total`; item có đúng các trường của đặc tả, không có trường định danh.
- **AC-2:** Phiên có 10+ hồ sơ được duyệt → thứ tự `NTG-01`, `NTG-02`, …, `NTG-10` (số, không phải chuỗi).
- **AC-3:** `approved_at` = thời điểm của dòng review `APPROVE` mới nhất; hồ sơ không có review `APPROVE` → `null`.
- **AC-4:** AUCTIONEER được phân công xem/xuất được; AUCTIONEER khác, ADMIN, BIDDER → 403; không token → 401;
  phiên không tồn tại → 404 (cho cả xem và xuất).
- **AC-5:** Xuất CSV không `include_identity` → đúng header HTTP, BOM UTF-8, tiêu đề 3 cột, đúng dòng/thứ tự, không có số
  giấy tờ, địa chỉ, số điện thoại trong nội dung.
- **AC-6:** Xuất CSV `include_identity=true` → thêm cột `Số giấy tờ` với đúng giá trị; vẫn không có địa chỉ/số điện thoại.
- **AC-7:** Xuất PDF → gọi `exporters.render_pdf("eligible_list.html", context)` với `context` đúng đặc tả (kể cả
  `id_number = None` khi không `include_identity`); response `application/pdf` + đúng `Content-Disposition`.
- **AC-8:** `render_pdf` ném `OSError` → 503 `PDF_ENGINE_UNAVAILABLE`, không ghi log xuất.
- **AC-9:** `format` thiếu/sai, `include_identity=abc` → 422 `VALIDATION_ERROR`.
- **AC-10:** Mỗi lần xuất thành công có đúng một dòng `EXPORT_ELIGIBLE_LIST` với `new_value` đúng quy tắc 6; xem danh
  sách không tạo log.
- **AC-11:** Phiên không có hồ sơ duyệt → danh sách rỗng (`total = 0`); CSV chỉ có dòng tiêu đề.

## Kế hoạch kiểm thử (Claude)

| AC | Test | File |
|---|---|---|
| AC-1, AC-3, AC-11 | `test_eligible_list_only_approved`, `test_eligible_list_approved_at`, `test_eligible_list_empty` | `tests/api/test_eligible_bidders_api.py` |
| AC-2 | `test_eligible_list_numeric_alias_order` | như trên |
| AC-4 | `test_eligible_permissions` | như trên |
| AC-5, AC-6, AC-11 | `test_export_csv_without_identity`, `test_export_csv_with_identity`, `test_export_csv_empty` | như trên |
| AC-7 | `test_export_pdf_context` (thay `exporters.render_pdf` bằng hàm giả), `test_export_pdf_real` (bỏ qua nếu WeasyPrint không nạp được) | như trên |
| AC-8 | `test_export_pdf_engine_unavailable` | như trên |
| AC-9 | `test_export_validation_error` | như trên |
| AC-10 | kiểm trong các test xuất ở trên | như trên |

Dữ liệu: dùng `create_registration_scenario`, `create_registration`, `add_review` trong `tests/factories.py`.

Môi trường: máy Windows hiện tại **không** chạy được WeasyPrint (thiếu Pango) → PDF thật sẽ trả 503; test PDF thật chỉ
chạy khi WeasyPrint nạp được (ví dụ trong Docker). Codex không cần cài thêm gì.

## Ghi chú triển khai (Codex)

- Sửa đúng 5 file router/schemas/service/repository/permissions của registrations. Hiện thực GET `/api/v1/sessions/{session_id}/eligible-bidders` và GET `/api/v1/sessions/{session_id}/eligible-bidders/export`.
- Chỉ chọn APPROVED; sắp số trong NTG tăng dần bằng SQL; lấy APPROVE mới nhất bằng truy vấn con (không truy vấn từng hồ sơ). DTO danh sách không có trường định danh.
- STAFF và AUCTIONEER phụ trách được xem/xuất; kiểm tra phiên tồn tại trước phạm vi. CSV có BOM, tùy chọn số giấy tờ; PDF gọi qua module exporters với đúng context. Không xuất địa chỉ/số điện thoại. Response xuất giữ header token gia hạn.
- Chỉ ghi EXPORT_ELIGIBLE_LIST và commit sau khi tạo xong nội dung; new_value có hậu tố +identity nếu cần. PDF thiếu thư viện hệ thống trả 503 và không ghi log.
- Mã lỗi: UNAUTHORIZED/FORBIDDEN qua dependency và permissions, NOT_FOUND, VALIDATION_ERROR, PDF_ENGINE_UNAVAILABLE. Không khác đặc tả, không thêm thư viện hay đổi template.
- Ruff check/format sạch. Không DB: 45 passed, 210 skipped. Toàn bộ test trên dgtt_test_codex: 254 passed, 1 skipped (PDF thật thiếu Pango); không có test đỏ tại thời điểm chạy. Test TASK-005 được Claude tạo sau khi lượt này đã thu thập test nên chưa nằm trong kết quả trên.
- Thử nhanh bằng httpx trên dgtt: staff đăng nhập, danh sách trả 200 (2 hồ sơ), CSV trả 200 text/csv; charset=utf-8 có BOM, PDF trả 503 PDF_ENGINE_UNAVAILABLE đúng môi trường. Dữ liệu mock trong test do Claude quản lý.

## Kết quả kiểm thử (Claude)

**Thời điểm:** 2026-11-25 22:58 (giờ Việt Nam) · **Kết luận:** DONE

**Lệnh đã chạy:**

| Lệnh | Kết quả |
|---|---|
| `ruff check .` · `ruff format --check .` | Sạch (107 file) |
| `pytest` (không DB) | 46 đạt, 2 hỏng, 241 bỏ qua. 2 hỏng là test 401 của **TASK-005** (endpoint POST chưa có, Codex đang làm) |
| `TEST_DATABASE_URL=…/dgtt_test pytest` (toàn bộ) | 256 đạt, 1 bỏ qua, 32 hỏng. **Cả 32 hỏng đều thuộc test TASK-005** (`test_results_api.py`, `test_result_concurrency.py`) vì task đó đang `IN_PROGRESS`. Mọi test của TASK-001…004 và các module cũ đạt → không hồi quy |
| Riêng TASK-004 (`test_eligible_bidders_api.py`) | **19 đạt**, 1 bỏ qua (`test_export_pdf_real`: WeasyPrint không nạp được Pango trên Windows) |

**Tiêu chí chấp nhận:**

| AC | Kết quả | Test |
|---|---|---|
| AC-1 | Đạt | `test_eligible_list_only_approved` |
| AC-2 | Đạt | `test_eligible_list_numeric_alias_order` (11 hồ sơ chèn xáo trộn; cả JSON và CSV) |
| AC-3 | Đạt | `test_eligible_list_approved_at` |
| AC-4 | Đạt | `test_eligible_permissions`, `test_list/export_without_token_returns_401`, `test_eligible_list_any_session_status` |
| AC-5 | Đạt | `test_export_csv_without_identity`, `test_export_csv_include_identity_false` |
| AC-6 | Đạt | `test_export_csv_with_identity` |
| AC-7 | Đạt (với hàm giả) | `test_export_pdf_context[False/True]`; PDF thật **chưa kiểm** trên máy này (bỏ qua) |
| AC-8 | Đạt | `test_export_pdf_engine_unavailable[OSError/ImportError]` |
| AC-9 | Đạt | `test_export_validation_error` |
| AC-10 | Đạt | kiểm trong các test xuất và `test_eligible_permissions` (403 không ghi log) |
| AC-11 | Đạt | `test_eligible_list_empty`, `test_export_csv_empty` |

**Review code (AGENTS.md Mục 4):**

- Chia lớp đúng; quyền qua `require_roles(STAFF, AUCTIONEER)` + `ensure_can_view_eligible` (dùng lại
  `is_assigned_auctioneer`), kiểm tra phiên tồn tại trước phạm vi.
- Một truy vấn lấy danh sách + `approved_at` (truy vấn con tương quan, không N+1); sắp theo số bằng
  `split_part(bidder_alias, '-', 2)::int`.
- Gọi `exporters.render_pdf` qua module; bắt `OSError`/`ImportError` → `AppError` 503. `log_activity` chỉ sau khi tạo xong
  nội dung, trước `commit`. Không xuất địa chỉ/số điện thoại; số giấy tờ chỉ khi `include_identity=true`.
- Dùng `utcnow()`; không thêm thư viện, không đổi template.

**Ghi chú nhỏ (không chặn DONE):**

- Sắp theo `split_part(...)::int` giả định mọi `bidder_alias` đúng dạng `NTG-<số>` (đúng với `format_alias`). Nếu sau này có
  mã dạng khác, truy vấn sẽ lỗi cast; hiện không có đường nào tạo mã khác.
- PDF thật cần kiểm lại một lần trong Docker (`test_export_pdf_real` sẽ tự chạy khi WeasyPrint nạp được).

## Quyết định của người dùng

_(Trống.)_

## Lịch sử

- 2026-11-25 22:15 | Claude | TODO | Tạo task

- 2026-11-25 22:03 | Codex | IN_PROGRESS | Nhận TASK-004 theo yêu cầu chạy liên tục TASK-004 và TASK-005.

- 2026-11-25 22:07 | Codex | REVIEW | Bàn giao TASK-004; 254 test đạt, 1 bỏ qua PDF thật do thiếu Pango; lint/format sạch.

- 2026-11-25 22:52 | Claude | TESTING | Nhận kiểm thử TASK-004.

- 2026-11-25 22:58 | Claude | DONE | 19/19 test TASK-004 đạt (1 bỏ qua PDF thật); không hồi quy.
