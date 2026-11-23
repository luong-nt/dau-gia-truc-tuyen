# DGTT – Prototype giao diện (v0.1)

Prototype giao diện tĩnh cho hệ thống đấu giá trực tuyến DGTT, do nhóm tự xây dựng theo thiết kế tại **Mục 4.7** của báo cáo.
Người phụ trách: Phan Văn Pháp (Frontend & UI/UX).

## Hiện trạng
- Chỉ là **HTML/CSS tĩnh**: chưa có JavaScript, chưa gọi API, chưa có cơ sở dữ liệu.
- Mọi dữ liệu trên màn hình (tài sản, họ tên, số tiền, mã NTG-xx) là **dữ liệu minh họa**.
- Các vòng tròn đỏ đánh số trên màn hình là chú thích, khớp với bảng mô tả thành phần trong báo cáo; xoá khi lập trình thật.

## Cách xem
Mở `index.html` bằng trình duyệt, chọn màn hình cần xem.

## Cấu trúc
```
index.html            Danh sách màn hình
screens/base.css      Quy ước màu, nút, nhãn trạng thái dùng chung (Bảng 4.7.2)
screens/scrXX-*.html  Từng màn hình SCR-01 … SCR-09
docs/mockups/         Ảnh PNG đã chèn trong báo cáo (DGTT_UI_*_v0.1.png)
```

## Việc cần làm tiếp (khi ghép với backend)
1. Thống nhất framework frontend và API với phần kiến trúc (Mục 4.3 – 4.5) và backend (Mục 4.6, 5.1.1, 5.1.2).
2. Tách các phần lặp lại (thanh điều hướng, menu quản lý, nhãn trạng thái) thành component.
3. Thay dữ liệu minh họa bằng dữ liệu từ API; phòng đấu giá nhận diễn biến qua kênh thời gian thực.
4. Làm theo máy trạng thái của khối đặt giá (Bảng 4.7.12): khoá nút khi chờ xác nhận, không tự gửi lại lệnh.
5. Kiểm thử theo bộ `DGTT_TESTCASE_v0.1.xlsx`.

## Giá trị đang là đề xuất, cần chốt
- Dung lượng tệp hồ sơ tối đa: 5 MB/tệp.
- Thời gian chờ xác nhận lệnh giá trước khi báo lỗi: 5 giây.
