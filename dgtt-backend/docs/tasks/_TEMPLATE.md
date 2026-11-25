# TASK-XXX: <Tiêu đề ngắn>

- **Trạng thái:** TODO
- **FR/NFR liên quan:** FR-xx, NFR-05
- **Module:** `app/modules/<module>`
- **Phụ thuộc:** (task phải DONE trước, hoặc "Không")
- **Người giao:** Claude · **Người làm:** Codex · **Người kiểm thử:** Claude

## Mô tả

<Làm gì, cho ai, tại sao. 2–5 câu.>

## Phạm vi file được sửa (Codex)

- `app/modules/<module>/router.py`
- `app/modules/<module>/schemas.py`
- `app/modules/<module>/service.py`
- `app/modules/<module>/repository.py`

Ngoài danh sách này: ghi lý do vào "Ghi chú triển khai" trước khi sửa.

## Đặc tả API

### 1. `METHOD /api/v1/...`

- **Vai trò:** ...
- **Request:** ...
- **Response 200/201:** ...
- **Lỗi:**

| Tình huống | HTTP | `code` |
|---|---|---|
| Chưa đăng nhập | 401 | `UNAUTHORIZED` |
| Sai vai trò | 403 | `FORBIDDEN` |
| ... | | |

## Quy tắc nghiệp vụ

1. ...

## Tiêu chí chấp nhận

- **AC-1:** ...
- **AC-2:** ...

## Kế hoạch kiểm thử (Claude)

| AC | Test | File |
|---|---|---|
| AC-1 | `test_...` | `tests/api/test_<module>_api.py` |

## Ghi chú triển khai (Codex)

_(Codex điền khi bàn giao: file đã sửa, endpoint, mã lỗi, khác biệt so với đặc tả, cách thử nhanh, test đang đỏ.)_

## Kết quả kiểm thử (Claude)

_(Claude điền khi kiểm thử: thời điểm, lệnh, số test đạt/hỏng, bảng AC, lỗi kèm bước tái hiện, kết luận.)_

## Quyết định của người dùng

_(Câu trả lời cho các câu hỏi khi task BLOCKED.)_

## Lịch sử

- YYYY-MM-DD HH:MM | Claude | TODO | Tạo task
