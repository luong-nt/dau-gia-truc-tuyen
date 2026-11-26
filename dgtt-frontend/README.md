# DGTT Frontend — Giao diện hệ thống đấu giá trực tuyến

Frontend viết bằng **React 18 + TypeScript + Vite**, gọi API của `dgtt-backend` (nhánh `backend`).
Thiết kế theo Mục 4.7 của báo cáo (prototype tĩnh trong `dgtt-frontend-prototype/`).
Người phụ trách: Phan Văn Pháp.

## 1. Chạy

Yêu cầu: Node.js 18 trở lên, backend đang chạy ở `http://localhost:8000` (xem README của `dgtt-backend`).

```bash
cd dgtt-frontend
npm install
npm run dev          # mở http://localhost:5173
```

Vite chuyển tiếp `/api` và `/ws` sang backend nên không cần cấu hình CORS.
Backend chạy ở địa chỉ khác thì đặt biến môi trường trước khi chạy:

```bash
DGTT_BACKEND=http://192.168.1.10:8000 npm run dev        # macOS/Linux
$env:DGTT_BACKEND="http://192.168.1.10:8000"; npm run dev  # Windows PowerShell
```

Tài khoản mẫu của backend (mật khẩu `Matkhau@123`): `admin`, `staff`, `auctioneer`, `bidder1`, `bidder2`.

Build bản chạy thật: `npm run build` → thư mục `dist/`. Khi triển khai, web server cần chuyển `/api` và `/ws`
về backend giống cấu hình proxy trong `vite.config.ts`.

## 2. Màn hình đã nối API

| Mã | Màn hình | Vai trò | API backend | FR |
|---|---|---|---|---|
| SCR-01 | Trang chủ, tra cứu phiên | Khách | `GET /sessions` | FR-07, 09 |
| SCR-02 | Chi tiết phiên, thông báo | Khách, Người tham gia | `GET /sessions/{id}` | FR-07 – 09 |
| SCR-03 | Đăng ký, đăng nhập, đăng xuất | Mọi vai trò | `/auth/*` | FR-01, 02 |
| SCR-04 | Nộp hồ sơ 3 bước, nộp bổ sung | Người tham gia | `POST /sessions/{id}/registrations`, `PUT /registrations/{id}` | FR-10, 12 |
| SCR-05 | Hồ sơ của tôi, trang cá nhân | Người tham gia | `GET /registrations/me`, `/auth/me`, `/auth/change-password` | FR-03, 13 |
| SCR-06 | Phòng đấu giá realtime | Người tham gia | `GET /sessions/{id}/state`, `POST /sessions/{id}/bids`, `ws /ws/sessions/{id}` | FR-15, 18 – 21 |
| — | Danh sách, tạo, sửa, công khai, hủy phiên | Nhân viên | `/sessions/manage`, `POST/PUT /sessions`, `/publish`, `/cancel` | FR-16, 17 |
| SCR-08 | Xét duyệt hồ sơ (3 bước đối chiếu, duyệt, bổ sung, từ chối) | Nhân viên | `/registrations`, `/checks`, `/decision`, tải giấy tờ | FR-11 – 13 |
| SCR-09 | Điều hành phiên, nhật ký lệnh giá, xác nhận/điều chỉnh kết quả | Đấu giá viên | `/open`, `/pause`, `/resume`, `/end`, `/bids?include_rejected`, `/results` | FR-17, 21 – 23 |
| — | Danh sách đủ điều kiện, xuất CSV/PDF | Nhân viên, Đấu giá viên | `/eligible-bidders`, `/export` | FR-14 |
| — | Quản lý tài khoản | Quản trị viên | `/users` | FR-04 |

**Chưa làm vì backend chưa có API:** quản lý tài sản và ảnh tài sản (TASK-007, TASK-008), thống kê, nhật ký, báo cáo
(TASK-010, TASK-011), xuất biên bản PDF (TASK-006). Trang `Tài sản` hiện chỉ hiển thị thông báo chờ API;
khi tạo phiên tạm nhập mã số tài sản.

## 3. Quy ước đã áp dụng

- **Thời gian:** backend trả UTC không kèm múi giờ → `parseUtc()` thêm `Z`, hiển thị GMT+7 dạng `HH:mm dd/MM/yyyy`.
  Khi gửi lên, giá trị ô ngày giờ được gửi kèm `+07:00`.
- **Tiền:** backend trả chuỗi Decimal (có thể dạng `1E+8`) → `money()` đọc thành số, `vnd()` hiển thị `100.000.000 đ`.
- **Token:** lưu trong `localStorage`; mỗi phản hồi có `X-Access-Token` thì thay token mới (gia hạn 30 phút, NFR-04).
  Gặp 401 thì báo hết phiên, không tự gửi lại thao tác cũ.
- **Lỗi:** backend trả `{code, message, details}`; giao diện hiển thị `message` tiếng Việt.
- **Phòng đấu giá (Bảng 4.7.12):**
  - mỗi lệnh có `transaction_code` (UUID); nút Gửi giá khóa trong lúc chờ xác nhận;
  - quá 5 giây chưa có phản hồi thì cho "Hỏi lại kết quả" bằng **cùng mã** (máy chủ trả kết quả cũ, không tạo lệnh trùng);
  - mất kết nối WebSocket thì khóa gửi giá, tự kết nối lại và nhận `session.snapshot` mới;
  - đồng hồ tính theo `end_time` và giờ máy chủ, không theo giờ máy người dùng;
  - giá tối thiểu trên giao diện chỉ là gợi ý; máy chủ quyết định chấp nhận hay từ chối.
- Ẩn menu/nút theo vai trò chỉ để điều hướng; mọi kiểm tra quyền vẫn do backend thực hiện (NFR-05).

## 4. Cấu trúc

```
src/
├── api/client.ts      # gọi API, token, lỗi, tải tệp, địa chỉ WebSocket
├── api/types.ts       # kiểu dữ liệu khớp schemas backend
├── auth/AuthContext.tsx
├── components/        # Layout (công khai / quản lý), Badge, hộp thoại lý do, phân trang
├── format.ts          # tiền, giờ GMT+7, nhãn trạng thái (Bảng 4.7.2)
└── pages/
    ├── Home, SessionDetail, Auth, Profile
    ├── bidder/        # RegistrationForm, MyRegistrations, AuctionRoom
    ├── manage/        # Sessions (danh sách + form), SessionManage, Reviews, Assets
    └── admin/Users
```

## 5. Đã chạy thử (26/11/2026)

Chạy với backend nhánh `backend` (commit `2f895ed`), PostgreSQL 16 và dữ liệu mẫu. Kiểm thử tự động bằng trình duyệt, các luồng đều đạt:

1. Khách xem trang chủ và chi tiết phiên.
2. Hai người tham gia cùng ở trong phòng: lượt của người này hiện ngay ở màn hình người kia, không cần tải lại.
3. Nhân viên tạo phiên rồi công khai.
4. Người tham gia nộp hồ sơ. Khi thiếu giấy tờ bắt buộc, nút Tiếp tục bị khóa.
5. Nhân viên đối chiếu đủ 3 tiêu chí; nút Duyệt chỉ bật khi cả 3 đều Đạt. Duyệt xong hệ thống cấp mã NTG-01.
6. Nhân viên yêu cầu bổ sung (có lý do và hạn). Người tham gia thấy lý do, nộp bổ sung, hồ sơ quay về Chờ duyệt.
7. Đấu giá viên tạm dừng phiên (bắt buộc lý do), người trong phòng nhận thông báo ngay. Sau đó đấu giá viên kết thúc sớm, hệ thống sinh kết quả dự kiến, đấu giá viên xác nhận.
8. Quản trị viên xem danh sách tài khoản.
