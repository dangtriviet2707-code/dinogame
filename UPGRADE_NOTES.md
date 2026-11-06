# DINO Fantasy Upgrade – Ghi chú bàn giao

## Đã tích hợp trong gói mã nguồn
- Luồng vào game mới: đăng nhập/đăng ký/chơi khách → sảnh nhà → chọn bản đồ → gameplay.
- Sảnh nhà dạng CSS/vector với nhân vật khủng long SVG có chuyển động nhún và vẫy đuôi.
- Ba chủ đề bản đồ; mỗi bản đồ có background SVG riêng.
- Gameplay có HP, giáp, thời gian miễn nhiễm ngắn, hiệu ứng nhận sát thương.
- Máy bay giới hạn nhịp thả bom; thiên thạch có quỹ đạo ngẫu nhiên và có thể va chạm người chơi.
- Bổ sung boss B để đồng bộ thứ tự D/C/B/A/S/Linh Khuyển/Ma Nữ/Ma Thần.
- Túi đồ, bốn ô trang bị, chỉ số HP/giáp/tốc độ/giảm hồi chiêu.
- Bảng loot riêng theo boss; D-A chỉ có Thường/Hiếm, S trở lên có cơ hội Huyền thoại.
- Độn thổ mở sau boss A; Biến hình mở sau Linh Khuyển; tia hắc ám có cooldown 3 giây.
- Chat thế giới; dùng bảng Supabase nếu cấu hình Supabase, nếu không thì lưu file JSON cục bộ.
- Bảng xếp hạng có hiển thị Champion Set cho người đứng đầu.
- API cấp vật phẩm admin và đổi mã độc quyền qua biến môi trường.
- Giữ lại `players.json` và cơ chế tự bổ sung trường mới để tương thích dữ liệu cũ.

## Cấu hình bổ sung
- `DINO_EXCLUSIVE_CODES`: danh sách mã độc quyền, phân cách bằng dấu phẩy.
- Chạy lại toàn bộ `supabase_schema.sql` trong Supabase SQL Editor để tạo bảng chat thế giới.

## Phím điều khiển mới
- `Q`: Độn thổ.
- `E`: Biến hình khủng long bay.
- `R`: Phun tia hắc ám khi đang biến hình.
- `↑` / `↓`: điều khiển độ cao khi đang biến hình.
- `Space` / `↑`: nhảy khi ở dạng thường.
- `↓`: cúi; `Shift`: lướt; `F`: phun lửa khi có hiệu lực.

## Giới hạn cần biết
- Bộ hình ảnh hiện tại là bộ minh họa SVG/CSS/Canvas tự chứa để chạy ngay, chưa phải bộ sprite sheet hoạt họa nhiều khung hình chuyên nghiệp. Có thể thay bằng artwork gốc khi có ảnh tham chiếu.
- Sảnh nhà có dữ liệu `home` tách theo tài khoản nhưng giao diện trang trí nhà và tính năng ghé thăm chưa được triển khai.
- Ba bản đồ có nền và chủ đề riêng; logic vật cản/boss cốt lõi vẫn dùng chung.
- Chat dùng bảng Supabase khi có cấu hình; nếu chạy JSON local trên Render thì lịch sử chat có thể mất khi filesystem tạm bị làm mới.
- Điểm và boss vẫn được gửi từ client; backend chặn giá trị vượt ngưỡng điểm/mốc boss và chỉ cấp loot cho boss mới, nhưng đây chưa phải mô hình chống gian lận tuyệt đối. Muốn xếp hạng cạnh tranh nghiêm túc cần chuyển mô phỏng kết quả quan trọng sang server hoặc dùng run-ticket có chữ ký.
- Chưa chạy được kiểm thử Flask end-to-end trong môi trường đóng gói hiện tại vì môi trường build không có Flask và không truy cập được package index. Đã kiểm tra cú pháp Python, cú pháp JavaScript, JSON người chơi và cấu trúc SVG.

## Bản vá lỗi xác thực, bảng xếp hạng, chat và bom (07/11/2026)
- Bổ sung đầy đủ các hàm lưu/đọc `players.json`, chuẩn hóa khóa tài khoản và tính hạng ở backend.
- Đồng bộ cấp độ theo kỷ lục điểm; bảng xếp hạng hiển thị hạng và có trạng thái lỗi/thử lại rõ ràng.
- Sửa phần chữ hạng bị vẽ đè lên dòng tiến hóa trong HUD khi đang chơi.
- Chat thế giới có trạng thái tải/lỗi, nút làm mới; khách chỉ xem, tài khoản đăng nhập mới gửi. Khi Supabase chat lỗi, backend chuyển sang lưu JSON local.
- Máy bay chỉ mang một quả bom mỗi lượt; bộ đếm toàn cục giới hạn tối đa một lần thả bom trong mỗi 900 frame ở tốc độ 60 FPS (xấp xỉ 15 giây).
- Đã kiểm tra cú pháp Python (`py_compile`) và JavaScript (`node --check`). Chưa chạy kiểm thử tích hợp Flask/Supabase trong môi trường đóng gói hiện tại.


## Bản vá Admin, lưu dữ liệu, trang bị và loot (07/11/2026)
- Admin mở hộp thoại nhập mật khẩu bằng phím dấu huyền (`) hoặc chạm tên tác giả 5 lần; backend xác minh mật khẩu.
- Khi dùng Supabase, `players.json` được nhập theo nguyên tắc insert-only: chỉ thêm ID chưa tồn tại, không ghi đè tài khoản có sẵn. Supabase được dùng làm nguồn chính và nhận cập nhật sau mỗi thao tác ghi.
- Khi chạy local, `players.json` được ghi nguyên tử để hạn chế hỏng file.
- Trang bị/mặc/tháo cập nhật ngay các chỉ số HP, giáp, tốc độ và hồi chiêu; vật phẩm tháo được trả lại túi.
- Thông báo loot thể hiện icon, tên, phẩm chất và hiệu ứng nổi.
- Đã kiểm tra cú pháp Python và JavaScript. Chưa chạy được kiểm thử tích hợp Flask/Supabase vì môi trường đóng gói không có các package tương ứng.

## Bản vá xác thực tài khoản + Admin 08/11/2026
- Login không còn giữ phiên cũ: sau khi xác thực thành công, session được xoá và gắn lại đúng storage key của tài khoản vừa đăng nhập.
- Login có thể tìm tài khoản theo key lưu trữ hoặc `name` bên trong JSON record, phù hợp hơn với dữ liệu Supabase legacy có ID khác username.
- Không tự nhận tài khoản nếu có nhiều record trùng tên; trường hợp mơ hồ sẽ bị từ chối thay vì vào nhầm tài khoản.
- Chuẩn hoá dữ liệu JSON từ Supabase nếu cột data trả về JSON dạng chuỗi.
- `ADMIN_PASSWORD` được đọc lại từ Environment tại thời điểm xác thực thay vì chỉ lấy một giá trị cố định khi import module.
- API diagnostics/admin status cũng phản ánh trạng thái `ADMIN_PASSWORD` hiện tại.
- API response có `Cache-Control: no-store` để tránh cache phiên/login cũ.


## Bản vá Admin / Tên tài khoản / Khủng long bay (08/11/2026)
- Sau khi xác thực Admin thành công, ô nhập lệnh Admin tự mở ngay.
- Sảnh nhà hiển thị rõ tên tài khoản và cấp độ từ player session hiện tại.
- Dạng biến hình sử dụng artwork pterosaur riêng, thay cho khối khủng long mặt đất có cánh.
- Khi biến hình, nhân vật bay độc lập trên không, có điều khiển Space/↑/↓ và cảm ứng, giới hạn độ cao an toàn; hết biến hình sẽ trở lại mặt đất.
