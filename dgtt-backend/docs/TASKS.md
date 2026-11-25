# Bảng công việc

> Chỉ **Claude** cập nhật file này. Trạng thái gốc nằm trong từng file task; khi lệch nhau, **file task là đúng**.
> Trạng thái: TODO · IN_PROGRESS · REVIEW · TESTING · CHANGES_REQUESTED · DONE · BLOCKED

Cập nhật lần cuối: 2026-11-25 23:20

## Đang theo dõi

| ID | Tiêu đề | FR | Module | Phụ thuộc | Trạng thái | Đang chờ |
|---|---|---|---|---|---|---|

## Backlog (chưa lập task)

| Dự kiến | Nội dung | FR | Module | Ghi chú |
|---|---|---|---|---|
| TASK-013 | **Lỗi:** tiền trong JSON in dạng số mũ (`"1E+8"`, `"5.00E+6"`) khi đọc từ DB | NFR-07 | dùng chung (schemas tiền) | Phát hiện khi kiểm thử TASK-005; ảnh hưởng sessions, bidding, results. Nên làm sớm |
| TASK-006 | Xuất biên bản kết quả PDF | FR-23 | results | Sau TASK-005 |
| TASK-007 | Người có tài sản + tài sản: thêm/sửa/xoá/tra cứu | FR-05, FR-06, FR-07 | assets | |
| TASK-008 | Upload/tải ảnh và tài liệu tài sản | FR-05, FR-07 | assets | Sau TASK-007 |
| TASK-009 | Người tham gia xem kết quả đã xác nhận | FR-23 | results | |
| TASK-010 | Thống kê và tra cứu nhật ký | FR-24, FR-26 | reports | |
| TASK-011 | Xuất báo cáo tổng hợp CSV/PDF | FR-25 | reports | |
| TASK-012 | Quy chế tạm dừng: có kéo dài `end_time` không | FR-17 | sessions | Cần người dùng quyết định trước |

## Đã xong

| ID | Tiêu đề | Ngày xong |
|---|---|---|
| [TASK-001](tasks/TASK-001-nop-ho-so-dang-ky.md) | Nộp hồ sơ đăng ký, xem hồ sơ của tôi | 2026-11-25 |
| [TASK-002](tasks/TASK-002-xet-duyet-ho-so.md) | Đối chiếu, xét duyệt, bổ sung, nộp lại hồ sơ | 2026-11-25 |
| [TASK-004](tasks/TASK-004-danh-sach-du-dieu-kien.md) | Danh sách người đủ điều kiện + xuất CSV/PDF | 2026-11-25 |
| [TASK-005](tasks/TASK-005-xac-nhan-dieu-chinh-ket-qua.md) | Xác nhận, điều chỉnh kết quả, đồng bộ trạng thái tài sản | 2026-11-25 |
| [TASK-003](tasks/TASK-003-tao-sua-phien-dau-gia.md) | Tạo/sửa phiên, lịch phiên công khai | 2026-11-25 |
| — | Khung dự án, auth, users, bidding, điều hành trạng thái phiên, scheduler | 2026-11-25 (trước khi dùng quy trình task) |
