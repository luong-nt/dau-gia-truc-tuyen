# Bảng công việc

> Chỉ **Claude** cập nhật file này. Trạng thái gốc nằm trong từng file task; khi lệch nhau, **file task là đúng**.
> Trạng thái: TODO · IN_PROGRESS · REVIEW · TESTING · CHANGES_REQUESTED · DONE · BLOCKED

Cập nhật lần cuối: 2026-11-27 00:25 (đợt này Claude triển khai, Codex kiểm thử — xem CLAUDE.md)

## Đang theo dõi

Đợt này Claude triển khai, Codex kiểm thử độc lập. Mọi task đã triển khai và bàn giao REVIEW.
`dgtt_test` 2026-11-27 00:10: 376 passed, 2 skipped, 1 failed (TC-RES-003: PDF thật cần Pango, lỗi môi trường).

| ID | Tiêu đề | FR | Module | Phụ thuộc | Trạng thái | Đang chờ |
|---|---|---|---|---|---|---|
| [TASK-006](tasks/TASK-006-xuat-bien-ban-ket-qua.md) | Xuất biên bản kết quả PDF | FR-23 | results | 005, 013 | REVIEW | Codex kiểm thử |
| [TASK-007](tasks/TASK-007-quan-ly-tai-san.md) | Thêm/sửa/xoá/ngừng/tra cứu tài sản | FR-05 – FR-07 | assets | 013 | REVIEW | Codex kiểm thử |
| [TASK-009](tasks/TASK-009-xem-ket-qua-chinh-thuc.md) | Người tham gia xem kết quả đã xác nhận | FR-23 | results | 006, 013 | REVIEW | Codex kiểm thử |
| [TASK-010](tasks/TASK-010-thong-ke-nhat-ky.md) | Thống kê hoạt động, tra cứu nhật ký | FR-24, FR-26 | reports | 013 | REVIEW | Codex kiểm thử |
| [TASK-011](tasks/TASK-011-xuat-bao-cao-ket-qua.md) | Xuất báo cáo tổng hợp kết quả CSV/PDF | FR-25 | reports | 010, 013 | REVIEW | Codex kiểm thử |
| [TASK-014](tasks/TASK-014-nguoi-co-tai-san.md) | Quản lý người có tài sản | FR-05 | assets | 007 | REVIEW | Codex kiểm thử |
| [TASK-008](tasks/TASK-008-anh-tai-lieu-tai-san.md) | Upload/tải/xoá ảnh, tài liệu tài sản | FR-05, FR-07 | assets | 007, 014 | REVIEW | Codex kiểm thử |

## Backlog (chưa lập task)

_(Trống: mọi mục backlog đã được lập task.)_

## Đã xong

| ID | Tiêu đề | Ngày xong |
|---|---|---|
| [TASK-001](tasks/TASK-001-nop-ho-so-dang-ky.md) | Nộp hồ sơ đăng ký, xem hồ sơ của tôi | 2026-11-25 |
| [TASK-002](tasks/TASK-002-xet-duyet-ho-so.md) | Đối chiếu, xét duyệt, bổ sung, nộp lại hồ sơ | 2026-11-25 |
| [TASK-003](tasks/TASK-003-tao-sua-phien-dau-gia.md) | Tạo/sửa phiên, lịch phiên công khai | 2026-11-25 |
| [TASK-004](tasks/TASK-004-danh-sach-du-dieu-kien.md) | Danh sách người đủ điều kiện + xuất CSV/PDF | 2026-11-25 |
| [TASK-005](tasks/TASK-005-xac-nhan-dieu-chinh-ket-qua.md) | Xác nhận, điều chỉnh kết quả, đồng bộ trạng thái tài sản | 2026-11-25 |
| [TASK-013](tasks/TASK-013-dinh-dang-tien-json.md) | Sửa lỗi tiền trong JSON dạng số mũ | 2026-11-26 |
| [TASK-012](tasks/TASK-012-quy-che-tam-dung.md) | Quy chế tạm dừng: cộng bù thời gian tạm dừng vào end_time | 2026-11-27 |
| — | Khung dự án, auth, users, bidding, điều hành trạng thái phiên, scheduler | 2026-11-25 (trước khi dùng quy trình task) |

## Ghi chú kiểm thử

- `tests/api/test_acceptance_cases.py::test_tc_res_003_confirm_result_and_export_minutes` cần WeasyPrint thật; trên máy
  Windows chưa có Pango nó sẽ đỏ (503) kể cả khi TASK-006 xong. Kiểm bằng Docker.
- `test_minutes_real_pdf` (TASK-006) tự bỏ qua khi máy không nạp được WeasyPrint.
