# Hướng dẫn chạy DGTT

Dùng **PowerShell**, mở tại thư mục gốc dự án. Chọn một trong hai cách chạy backend dưới đây.

## 1. Chạy bằng Docker (nhanh nhất)

Cài và mở **Docker Desktop**, sau đó chạy:

```powershell
cd .\dgtt-backend
docker compose up -d --build
```

Đợi backend khởi động xong rồi tạo tài khoản và dữ liệu mẫu:

```powershell
docker compose logs -f backend
# Khi thấy Application startup complete, nhấn Ctrl+C để thoát xem log.
docker compose exec backend python -m seeds.seed_dev
```

Mở Swagger: <http://localhost:8000/docs>.

- Lần sau bật lại: `docker compose up -d`.
- Sau khi sửa code: `docker compose up -d --build backend`.
- Dừng dự án, giữ dữ liệu: `docker compose down`.

## 2. Chạy bằng Python local (để sửa code)

Cần **Python 3.12** và Docker Desktop để chạy PostgreSQL. Từ thư mục gốc:

```powershell
cd .\dgtt-backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d db
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m seeds.seed_dev
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Nếu đã có `.venv` thì bỏ qua bước tạo. Nếu backend Docker đang chạy, dùng `docker compose stop backend` trước khi bật Uvicorn để tránh trùng cổng `8000`.

Các lần sau chỉ cần bật database và chạy lại lệnh Uvicorn. Nhấn `Ctrl+C` để dừng server.

Nếu dùng PostgreSQL riêng, tạo database và sửa kết nối trong `.env`; không cần bật container `db`. Kết nối mặc định của backend local:

```dotenv
DATABASE_URL=postgresql+asyncpg://dgtt:dgtt@localhost:5432/dgtt
```

## 3. Đăng nhập thử

Sau khi seed, các tài khoản dùng chung mật khẩu **`Matkhau@123`**:

| Tài khoản | Vai trò |
|---|---|
| `admin` | Quản trị tài khoản |
| `staff` | Thiết lập phiên, xét duyệt hồ sơ |
| `auctioneer` | Điều hành phiên, xác nhận kết quả |
| `bidder1`, `bidder2` | Người tham gia đấu giá |

Trong Swagger, mở `POST /api/v1/auth/login` → **Try it out**, gửi:

```json
{"login": "bidder1", "password": "Matkhau@123"}
```

Sao chép `access_token` → bấm **Authorize** → dán token để gọi API cần đăng nhập.

Phiên mẫu có thời gian trả giá **60 phút từ lúc seed**. Chạy seed lại khi đã có tài khoản `admin` sẽ bỏ qua, không gia hạn phiên cũ.

## 4. Kết nối pgAdmin 4

Bảo đảm PostgreSQL đang chạy. Trong pgAdmin chọn **Servers → Register → Server…**:

| Trường | Giá trị |
|---|---|
| Name | `DGTT Local` |
| Host name/address | `127.0.0.1` |
| Port | `5432` |
| Maintenance database | `dgtt` |
| Username | `dgtt` |
| Password | `dgtt` |

Bấm **Save** → **Databases → dgtt → Schemas → public → Tables**. Chuột phải bảng → **View/Edit Data → All Rows** để xem dữ liệu.

## 5. Xem giao diện và lưu ý

- Mở `dgtt-frontend-prototype/index.html` bằng trình duyệt. Đây là HTML/CSS tĩnh, chưa kết nối backend; thao tác thật qua Swagger.
- Backend chưa có trang chủ `/`; dùng đường dẫn `/docs`.
- Xuất PDF trên Windows cần thư viện hệ thống; dùng cách Docker nếu gặp lỗi thiếu thư viện.
- Backend chạy **1 worker** để WebSocket và scheduler hoạt động đúng.
