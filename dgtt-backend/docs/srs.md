# Yêu cầu hệ thống DGTT (trích Mục 3.3 báo cáo)

> Bản trích để agent tra cứu. Nếu báo cáo gốc thay đổi, Claude cập nhật lại file này.
> Khi SRS mâu thuẫn với schema: **schema `sql/dgtt_schema_postgresql.sql` là chuẩn** (xem `AGENTS.md`).

## Tác nhân

1. **Quản trị viên (ADMIN):** quản lý tài khoản, phân quyền, thống kê tổng hợp, tra cứu nhật ký. Quyền quản trị kỹ thuật
   **không** mặc nhiên bao gồm quyền duyệt hồ sơ hoặc xác nhận kết quả nghiệp vụ.
2. **Nhân viên công ty đấu giá (STAFF):** quản lý tài sản và thông báo; tiếp nhận hồ sơ, đối chiếu giấy tờ và tiền đặt trước,
   xét duyệt; lập danh sách đủ điều kiện và thiết lập phiên đấu giá.
3. **Đấu giá viên (AUCTIONEER):** xem danh sách đủ điều kiện, điều hành phiên được phân công, theo dõi diễn biến trả giá,
   xử lý ngoại lệ theo quy chế và kiểm tra, xác nhận biên bản kết quả.
4. **Người tham gia đấu giá (BIDDER):** quản lý tài khoản, tra cứu thông tin công khai, nộp và bổ sung hồ sơ, theo dõi xét duyệt,
   trả giá khi đủ điều kiện và xem kết quả trong phạm vi được phép. **Khách** chưa đăng nhập được xem thông tin công khai
   và đăng ký tài khoản; có tài khoản chưa đồng nghĩa với đủ điều kiện tham gia phiên.

Người có tài sản là bên liên quan, không có tài khoản. Phạm vi sau phiên gồm xác nhận và lưu trữ kết quả; chưa gồm thanh toán,
bàn giao hay chuyển quyền sở hữu.

## Yêu cầu chức năng

### Nhóm 1: Quản lý tài khoản và phân quyền

| Mã | Tên | Mô tả | Tác nhân | Ưu tiên |
|---|---|---|---|---|
| FR-01 | Đăng ký tài khoản người tham gia | Khách tạo tài khoản bằng họ tên, email, số điện thoại, tên đăng nhập và mật khẩu. Kiểm tra trường bắt buộc, định dạng và tính duy nhất của email/tên đăng nhập; gán vai trò Người tham gia. Việc đăng ký tài khoản không thay thế hồ sơ đăng ký từng phiên. | Khách | Cao |
| FR-02 | Đăng nhập và đăng xuất | Đăng nhập bằng tên đăng nhập/email và mật khẩu, điều hướng theo quyền. Từ chối tài khoản bị khóa hoặc thông tin không hợp lệ; hỗ trợ đăng xuất. | 4 vai trò | Cao |
| FR-03 | Quản lý thông tin cá nhân và đổi mật khẩu | Cập nhật thông tin liên hệ và đổi mật khẩu sau khi xác thực mật khẩu hiện tại. Thay đổi hồ sơ cá nhân không làm thay đổi bản thông tin đã nộp trong hồ sơ đấu giá; sửa hồ sơ đã nộp tuân theo FR-12. | 4 vai trò | Trung bình |
| FR-04 | Quản lý tài khoản và phân quyền | Quản trị viên tìm kiếm, lọc tài khoản, tạo tài khoản Nhân viên/Đấu giá viên, gán quyền và khóa/mở khóa. Mọi thay đổi quyền phải ghi nhật ký; không được dùng thay đổi quyền để sửa lịch sử nghiệp vụ. | Quản trị viên | Cao |

### Nhóm 2: Quản lý thông tin tài sản đấu giá

| Mã | Tên | Mô tả | Tác nhân | Ưu tiên |
|---|---|---|---|---|
| FR-05 | Thêm và cập nhật tài sản | Nhân viên nhập mã tài sản duy nhất, tên, mô tả, thông tin người có tài sản, hồ sơ liên quan và ảnh JPG/PNG. Giá khởi điểm, bước giá và lịch thiết lập theo từng phiên tại FR-16. Khi đã công khai, các thay đổi phải có phiên bản, lý do và người thực hiện; không sửa cấu hình giá khi phiên đang diễn ra. | Nhân viên | Cao |
| FR-06 | Xóa hoặc chuyển trạng thái tài sản | Chỉ xóa tài sản chưa gắn với hồ sơ/phiên. Tài sản đã có lịch sử chỉ được lưu trữ hoặc ngừng sử dụng. Trạng thái phản ánh vòng đời hợp lệ, không chuyển tùy ý; có kết quả đấu giá chưa đồng nghĩa đã bàn giao. Tài sản đấu giá không thành có thể gắn với phiên tổ chức lại. | Nhân viên | Trung bình |
| FR-07 | Tra cứu và xem chi tiết tài sản | Tìm theo tên/mã, lọc theo giá khởi điểm hoặc trạng thái phiên; xem mô tả, ảnh, thông báo liên quan. Khách và Người tham gia chỉ xem tài sản đã công khai; hồ sơ nội bộ chỉ hiển thị cho người có quyền. | 4 vai trò và Khách | Cao |

### Nhóm 3: Quản lý thông báo và lịch tổ chức đấu giá

| Mã | Tên | Mô tả | Tác nhân | Ưu tiên |
|---|---|---|---|---|
| FR-08 | Tạo và công khai thông báo | Nhân viên soạn và công khai thông báo gắn với tài sản/phiên: giá khởi điểm, bước giá, tiền đặt trước, điều kiện tham gia, hạn nhận hồ sơ/nộp tiền, thời gian tổ chức và quy chế. Lưu phiên bản khi thay đổi; không âm thầm thay điều kiện đã công khai. | Nhân viên | Cao |
| FR-09 | Xem thông báo và lịch đấu giá | Xem thông báo đã công khai và lịch theo trạng thái nhận hồ sơ, sắp diễn ra, đang diễn ra hoặc đã kết thúc. Thể hiện rõ các hạn và thời gian phiên theo múi giờ thống nhất. | 4 vai trò và Khách | Trung bình |

### Nhóm 4: Quản lý hồ sơ đăng ký tham gia đấu giá

| Mã | Tên | Mô tả | Tác nhân | Ưu tiên |
|---|---|---|---|---|
| FR-10 | Nộp hồ sơ đăng ký từng phiên | Người tham gia chọn phiên đang nhận hồ sơ, nhập thông tin và tải giấy tờ. Kiểm tra hạn nộp, trường bắt buộc, loại/dung lượng tệp và đăng ký trùng trước khi ghi nhận Chờ duyệt. Mỗi người tối đa một hồ sơ hiệu lực trong một phiên; lưu thời điểm nộp và bản thông tin đã gửi. | Người tham gia | Cao |
| FR-11 | Đối chiếu điều kiện và tiền đặt trước | Nhân viên ghi nhận riêng kết quả kiểm tra giấy tờ, điều kiện tham gia và tiền đặt trước; lưu căn cứ, người kiểm tra và thời điểm. Chứng từ người tham gia tải lên chỉ là đầu vào đối chiếu, không tự chứng minh tiền đã nhận. Xác nhận thủ công, chưa tích hợp ngân hàng. | Nhân viên | Cao |
| FR-12 | Xét duyệt và yêu cầu bổ sung | Nhân viên xử lý hồ sơ Chờ duyệt thành Đã duyệt, Yêu cầu bổ sung hoặc Từ chối. Chỉ duyệt khi mọi điều kiện bắt buộc, gồm tiền đặt trước, đã đạt. Bổ sung/từ chối phải có lý do; yêu cầu bổ sung có hạn. Người tham gia sửa nội dung được yêu cầu và gửi lại đúng hạn, hồ sơ về Chờ duyệt; lưu lịch sử từng lần nộp và quyết định. | Nhân viên, Người tham gia | Cao |
| FR-13 | Theo dõi trạng thái và phản hồi hồ sơ | Người tham gia xem hồ sơ của mình, trạng thái, hạn bổ sung, lý do và lịch sử phản hồi. Nhân viên tìm kiếm/lọc hồ sơ theo phiên và trạng thái; hiển thị thông báo khi có quyết định. Không cho người tham gia xem giấy tờ của người khác. | Người tham gia, Nhân viên | Trung bình |

### Nhóm 5: Quản lý danh sách người tham gia

| Mã | Tên | Mô tả | Tác nhân | Ưu tiên |
|---|---|---|---|---|
| FR-14 | Lập danh sách người đủ điều kiện | Tổng hợp người có hồ sơ Đã duyệt và điều kiện còn hiệu lực vào danh sách từng phiên. Nhân viên và Đấu giá viên phụ trách tra cứu; lưu căn cứ và lịch sử nếu điều kiện thay đổi. Không thêm người chưa được duyệt bằng sửa danh sách thủ công. | Nhân viên, Đấu giá viên | Cao |
| FR-15 | Kiểm soát phòng đấu giá và xuất danh sách | Kiểm tra tại máy chủ quyền vào phòng và quyền gửi giá theo danh sách đủ điều kiện của đúng phiên. Nhân viên/Đấu giá viên phụ trách xuất danh sách theo quyền; thông tin định danh chỉ xuất khi cần, không công khai giấy tờ và thông tin liên hệ. | Người tham gia, Nhân viên, Đấu giá viên | Trung bình |

### Nhóm 6: Quản lý và điều hành phiên đấu giá trực tuyến

| Mã | Tên | Mô tả | Tác nhân | Ưu tiên |
|---|---|---|---|---|
| FR-16 | Thiết lập phiên và phân công | Nhân viên tạo mã phiên duy nhất, gắn một tài sản, phân công một Đấu giá viên; giá khởi điểm > 0, bước giá > 0, tiền đặt trước và quy tắc lượt giá đầu. Hạn nhận hồ sơ và hạn nộp tiền đều trước giờ bắt đầu; giờ kết thúc sau giờ bắt đầu. Lưu cấu hình phiên bản khi công khai; không thay cấu hình giá trong phiên đang diễn ra. | Nhân viên | Cao |
| FR-17 | Điều hành trạng thái phiên | Đấu giá viên được phân công mở phiên khi đủ điều kiện, tạm dừng và tiếp tục theo quy chế; ghi lý do và thời điểm xử lý sự cố. Máy chủ đóng nhận giá khi đến hạn. Kết thúc trước hạn hoặc hủy phải có căn cứ, quyền xử lý và nhật ký. | Đấu giá viên | Cao |
| FR-18 | Tham gia phòng và gửi giá | Người tham gia đủ điều kiện vào đúng phòng, xem cấu hình đã công khai và gửi giá khi phiên đang diễn ra. Mỗi lệnh nhận phản hồi đã chấp nhận hoặc bị từ chối với lý do; giao diện không coi lệnh đã gửi là được chấp nhận khi chưa có xác nhận máy chủ. | Người tham gia | Cao |
| FR-19 | Đồng bộ diễn biến và thời gian | Cập nhật giá cao nhất, các lượt giá và trạng thái phiên đến các bên trong phòng. Đồng hồ dựa trên thời gian kết thúc do máy chủ cung cấp. Dùng mã người tham gia trên giao diện chung, không công khai giấy tờ. Khi kết nối lại, đồng bộ trạng thái máy chủ. | Người tham gia, Đấu giá viên | Cao |
| FR-20 | Kiểm tra hợp lệ và thứ tự trả giá | Máy chủ kiểm tra trạng thái/thời hạn phiên, quyền người gửi và giá. P = P0 + k × Δ (Δ > 0, k nguyên không âm); lượt đầu có được bằng P0 hay không theo quy chế. Từ lượt sau, P phải lớn hơn giá cao nhất đã chấp nhận. Kiểm tra và ghi nguyên tử theo thứ tự máy chủ; hai lệnh cùng giá chỉ tối đa một lệnh được nhận. Từ chối rõ lý do. | Người tham gia; hệ thống | Cao |

### Nhóm 7: Lịch sử trả giá và kết quả đấu giá

| Mã | Tên | Mô tả | Tác nhân | Ưu tiên |
|---|---|---|---|---|
| FR-21 | Lưu và tra cứu lịch sử trả giá | Lưu lượt giá đã chấp nhận với mã giao dịch, mã phiên, người gửi, mức giá, thời gian, thứ tự máy chủ; không sửa/xóa. Nhân viên/Đấu giá viên tra cứu theo nhiệm vụ; Người tham gia xem diễn biến phiên mình tham gia bằng mã ẩn danh. Ghi cả lệnh bị từ chối để kiểm tra sự cố. | Nhân viên, Đấu giá viên, Người tham gia | Cao |
| FR-22 | Tổng hợp kết quả dự kiến | Khi đóng phiên, khóa nhận giá và tổng hợp giá cao nhất, người tương ứng cùng lịch sử để Đấu giá viên kiểm tra. Chưa tự công bố trúng chính thức. Phiên không có giá hợp lệ, sự cố hay trường hợp đặc biệt được ghi nhận để xử lý trước khi xác nhận tại FR-23. | Đấu giá viên; hệ thống | Cao |
| FR-23 | Kiểm tra và xuất biên bản kết quả | Đấu giá viên phụ trách kiểm tra kết quả dự kiến, ghi nhận xử lý ngoại lệ và xác nhận để công bố/xuất biên bản. Phân biệt bản dự thảo và bản đã xác nhận; các bên xem theo quyền. Điều chỉnh bằng phiên bản mới có lý do và lịch sử. Xác nhận phần mềm không thay thế chữ ký pháp lý. | Đấu giá viên, Nhân viên, Người tham gia | Trung bình |

### Nhóm 8: Thống kê, báo cáo và giám sát

| Mã | Tên | Mô tả | Tác nhân | Ưu tiên |
|---|---|---|---|---|
| FR-24 | Thống kê hoạt động | Quản trị viên/Nhân viên xem số tài sản, hồ sơ theo trạng thái và phiên theo kết quả trong khoảng thời gian; tách phiên chờ xác nhận với phiên đã có kết quả chính thức. Số liệu truy vết được đến dữ liệu chi tiết theo quyền. | Quản trị viên, Nhân viên | Trung bình |
| FR-25 | Xuất báo cáo tổng hợp kết quả | Lọc và xuất CSV/PDF tổng hợp kết quả, giá trúng đã xác nhận theo thời kỳ. Báo cáo ghi thời điểm tạo và điều kiện lọc; không cộng kết quả dự kiến vào tổng giá trúng chính thức. | Quản trị viên, Nhân viên | Thấp |
| FR-26 | Ghi và tra cứu nhật ký hoạt động | Ghi các thao tác quan trọng: đăng nhập, đổi quyền, xác nhận tiền đặt trước, xét/bổ sung hồ sơ, sửa cấu hình, mở/tạm dừng/đóng phiên, xác nhận/điều chỉnh kết quả. Lưu người thực hiện, thời điểm, đối tượng và thay đổi; Quản trị viên tra cứu, không sửa nội dung nhật ký. | Quản trị viên; hệ thống | Trung bình |

## Yêu cầu phi chức năng

| Mã | Nhóm | Tên | Mô tả & ngưỡng | Ưu tiên |
|---|---|---|---|---|
| NFR-01 | Hiệu năng | Thời gian phản hồi | Với 50 người dùng đồng thời, ≥ 95% thao tác đăng nhập, tra cứu, xử lý hồ sơ phản hồi ≤ 2 giây (không tính tải tệp). | Cao |
| NFR-02 | Hiệu năng | Độ trễ đồng bộ phòng | Với 50 người dùng, ≥ 95% sự kiện giá/trạng thái hiển thị ≤ 1 giây từ lúc máy chủ chấp nhận; kết nối lại phải đồng bộ giá và trạng thái mới nhất. | Cao |
| NFR-03 | Hiệu năng, đồng thời | Tải và tranh chấp giá | 50 người dùng và 50 lệnh giá gần cùng lúc: phản hồi xử lý đúng ≥ 99% (gồm từ chối đúng quy tắc). Không mất/ghi đè giá đã chấp nhận; mọi lệnh có thứ tự máy chủ. | Cao |
| NFR-04 | Bảo mật | Mật khẩu và phiên | Băm có muối bcrypt/Argon2; không lưu/ghi log mật khẩu rõ. HTTPS. Phiên hết hạn sau 30 phút không tương tác; thao tác hợp lệ trong phòng được tính tương tác; yêu cầu đăng nhập lại, không tự gửi lại giá cũ. | Cao |
| NFR-05 | Bảo mật | Vai trò và phạm vi dữ liệu | Kiểm tra quyền ở máy chủ cho mọi API: vai trò, chủ sở hữu hồ sơ, phân công phiên. Truy cập trái phép bị từ chối: 401 khi chưa xác thực, 403 khi không đủ quyền. Không trả giấy tờ định danh trong API công khai. | Cao |
| NFR-06 | Tin cậy, toàn vẹn | Bảo toàn lịch sử và kết quả | Giao dịch nhận giá ACID. Không sửa/xóa giá đã chấp nhận; kết quả điều chỉnh lưu phiên bản mới kèm căn cứ. Không có hai người cùng giữ một lượt giá hợp lệ tại cùng mức. | Cao |
| NFR-07 | Khả năng sử dụng | Giao diện và phản hồi rõ ràng | Giao diện tiếng Việt; phân biệt gửi hồ sơ với được duyệt, gửi giá với giá đã nhận. Lỗi trường nhập phản hồi ≤ 1 giây. | Trung bình |
| NFR-08 | Tương thích | Trình duyệt, màn hình, in | Chrome, Edge, Firefox trên máy tính và Chrome Android; ≥ 1280×720 và rộng 360 px. In danh sách/biên bản không mất cột, không lộ dữ liệu ngoài quyền. | Trung bình |
| NFR-09 | Bảo trì | Kiểm thử được và truy vết | Tách mô-đun tài khoản, hồ sơ, phiên, kết quả để kiểm thử độc lập. Có dữ liệu mẫu cho hồ sơ thiếu, bổ sung, quá hạn, tiền chưa xác nhận, trả giá đồng thời, phiên sự cố. Mỗi FR/NFR có ca kiểm thử. | Cao |
| NFR-10 | Bảo trì | Chuẩn hóa mã nguồn | Quy tắc đặt tên thống nhất, tách cấu hình khỏi mã, quản lý trên Git; commit gắn với yêu cầu/lỗi và được xem xét trước khi hợp nhất. | Trung bình |
