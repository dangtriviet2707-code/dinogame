# Viet Legends – Long Vương (v1.7)

Game khủng long 2D chạy trên trình duyệt, backend Python Flask. Phiên bản nâng cấp có sảnh nhà riêng, chọn bản đồ, gameplay HP, boss, loot trang bị, kỹ năng và chat thế giới.

## Chạy local

```bash
pip install -r requirements.txt
python app.py
```

Mở `http://localhost:4000`. Khi chưa cấu hình Supabase, game dùng `data/players.json` để chạy thử.

## Điều khiển

- Space / mũi tên lên: nhảy.
- Mũi tên xuống: cúi.
- Shift hoặc nút **NÉ**: lướt né nhanh.
- Giữ F hoặc giữ nút **PHUN LỬA**: bắn lửa khi đã nhặt bình lửa.
- Trên điện thoại: dùng các nút tròn NÉ và PHUN LỬA ở góc dưới bên phải.

## Khôi phục quyền Admin

- Truy cập trực tiếp `https://DOMAIN-GAME/admin` để mở Admin Panel. Nếu chưa đăng nhập, trang này hiện ô mật khẩu và gọi `/api/admin` để xác thực phía server.
- Mật khẩu Admin được đọc duy nhất từ biến `ADMIN_PASSWORD` trong Environment của Render; không được nhúng vào frontend hoặc source code.
- Sau khi đăng nhập, Admin Panel có danh sách người chơi, tìm kiếm, ID, cấp/điểm/boss/vật phẩm, trang bị và trạng thái kết nối storage.

Mở xác thực Admin: nhấn phím dấu huyền (`) trên máy tính hoặc chạm dòng tác giả 5 lần liên tiếp trên điện thoại. Một hộp thoại mật khẩu Admin sẽ xuất hiện; nhập mật khẩu và xác nhận. Sau khi xác thực, nhấn lại phím ` hoặc chạm 5 lần để mở ô lệnh quản trị. Các lệnh hỗ trợ:

```text
/speed n|auto
/god on|off
/jump n
/fire on|off
/off
/help
```

Đặt `ADMIN_PASSWORD` trong Environment Variables của Render. Không đặt mật khẩu trong mã nguồn, frontend, Git hoặc gửi mật khẩu qua chat. Sau khi xác thực, các lệnh `/help`, `/speed`, `/god`, `/jump`, `/fire`, `/off` hoạt động trong phiên đăng nhập.

## Thiết lập Supabase

1. Tạo project tại Supabase.
2. Mở **SQL Editor**, chạy toàn bộ nội dung file `supabase_schema.sql` (bao gồm bảng người chơi và chat thế giới).
3. Trong Supabase Project Settings -> API, lấy Project URL và `service_role` secret.
4. Trong Render -> dịch vụ DINO -> **Environment**, thêm:
   - `SUPABASE_URL`: Project URL.
   - `SUPABASE_SERVICE_ROLE_KEY`: service_role secret.
   - `SUPABASE_TABLE`: tên bảng Supabase CŨ đang chứa dữ liệu người chơi (gói hiện tại mặc định `dino_players`; nếu bản cũ dùng tên khác, đổi biến này, không tạo bảng mới).
   - `STORAGE_MODE`: `supabase` trên Render để bắt buộc dùng Supabase và **không** âm thầm fallback sang JSON.
   - `ADMIN_PASSWORD`: mật khẩu Admin mới.
   - `DINO_EXCLUSIVE_CODES`: danh sách mã trang bị độc quyền, phân cách bằng dấu phẩy.
   - `SESSION_SECRET`: chuỗi bí mật ngẫu nhiên dài (Render có thể tự tạo).
   - `BASE_URL`: URL HTTPS của dịch vụ Render.
5. Deploy lại.

**Bảo mật:** `SUPABASE_SERVICE_ROLE_KEY` chỉ được lưu trong Environment Variables của Render. Tuyệt đối không đặt key này trong `public/index.html`, không commit vào Git và không chia sẻ công khai. Bảng bật Row Level Security và không cấp quyền cho `anon`/`authenticated`; backend Flask mới được ghi/đọc bằng service role.

## Chuyển dữ liệu cũ

Khi ứng dụng khởi động với Supabase đã cấu hình:
- Nếu bảng `dino_players` còn trống, server tự nhập toàn bộ tài khoản từ `data/players.json` một lần.
- Nếu bảng đã có dữ liệu, server không ghi đè bằng JSON cũ.
- Dữ liệu JSON vẫn được giữ làm snapshot dự phòng; khi Supabase bật, mọi lần đọc/ghi chính thức đều đi qua Supabase.
- Nếu Supabase lỗi, API trả lỗi thay vì báo lưu thành công giả. Với `STORAGE_MODE=supabase`, ứng dụng cũng dừng khởi động nếu cấu hình Supabase không đầy đủ hoặc client không thể khởi tạo, tránh tình trạng tài khoản cũ biến mất do fallback JSON.

Trước khi deploy, hãy giữ lại bản ZIP và sao lưu file `data/players.json` mới nhất từ máy chủ cũ nếu có dữ liệu phát sinh sau thời điểm tạo ZIP. Bản JSON trong ZIP chỉ chứa snapshot đi kèm gói nguồn.

## Triển khai Render

- Root Directory: `dino` nếu kho Git chứa thư mục `dino/`; nếu nội dung trong `dino/` đã nằm ở root thì để trống.
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
- Health Check Path: `/healthz`

Render free có thể spin down khi không hoạt động. Supabase giữ dữ liệu bền vững độc lập với filesystem tạm của Render.


## Tính năng phiên bản Fantasy Upgrade

- Luồng vào game: đăng nhập/đăng ký hoặc chơi khách -> nhà riêng -> chọn 1 trong 3 map -> gameplay toàn màn hình.
- Chơi khách lưu kỷ lục tạm trên trình duyệt; đăng ký mới có thể chuyển các chỉ số cơ bản sang tài khoản.
- Ba chủ đề map: Khởi nguyên, Kỷ nguyên tiền sử, Khu vườn trên mây.
- HP, giáp, miễn thương ngắn sau khi trúng đòn; máy bay giới hạn nhịp thả bom và thiên thạch có quỹ đạo ngẫu nhiên.
- Trang bị 4 vị trí: mũ, áo, quần, giày; phẩm chất Thường, Hiếm, Huyền thoại, Độc quyền.
- Boss D đến A có loot Thường/Hiếm; boss S và boss đặc biệt có cơ hội loot Huyền thoại.
- Độn thổ mở sau boss A; Biến hình khủng long bay mở sau Linh Khuyển; tia hắc ám có hồi chiêu 3 giây.
- Chat thế giới cần đăng nhập để gửi tin. Nếu dùng Supabase, chạy schema mới để tạo bảng chat.
- Mã độc quyền cấu hình bằng `DINO_EXCLUSIVE_CODES`; admin có thể cấp vật phẩm qua API quản trị sau khi xác thực admin.

Lưu ý: giao diện map và sảnh hiện dùng minh họa vector/CSS/emoji để bảo đảm gói chạy ngay không phụ thuộc bộ ảnh ngoài. Có thể thay bằng sprite sheet và background vẽ riêng ở bước hoàn thiện mỹ thuật.

## Bản vá 07/11/2026
Bản này bổ sung lại các hàm lưu tài khoản và tính hạng phía máy chủ, sửa hiển thị hạng trong HUD, cải thiện bảng xếp hạng/chat và giới hạn bom máy bay ở tối đa một lần thả mỗi khoảng 15 giây. Chạy local vẫn có thể dùng `players.json`, không bắt buộc cấu hình Supabase.

## Bản vá hoàn thiện Admin, dữ liệu và trang bị (07/11/2026)
- Admin: phím ` trên máy tính hoặc chạm tên tác giả 5 lần trên điện thoại mở hộp thoại nhập mật khẩu riêng; xác thực vẫn được kiểm tra ở backend.
- Lưu người chơi: Supabase là nguồn dữ liệu chính khi đã cấu hình. Lần khởi động đầu, dữ liệu từ `players.json` chỉ được nhập cho các ID chưa có trong DB; dữ liệu hiện hữu trên Supabase không bị ghi đè. Mỗi lần cập nhật sẽ upsert bản ghi người chơi. Khi chạy local, JSON được ghi nguyên tử.
- Trang bị: mặc/tháo theo đúng bốn ô mũ, áo giáp, quần, giày; chỉ số được tính lại ngay sau thao tác.
- Loot: thông báo chúc mừng có biểu tượng, tên và phẩm chất, tự ẩn sau vài giây.
- Lưu ý: để dữ liệu tồn tại bền vững trên Render, cần cấu hình Supabase. File JSON trên filesystem Render có thể bị mất khi dịch vụ được tạo lại.

## Long Vương v1.6

Xem `RELEASE_v1.6_LONG_VUONG_COMPLETE.md` và `PHASE2_TO_PHASE8_STATUS.md` để biết các phần sự kiện Đại Dương, combat theo lượt server-side, hội thoại, nhận thưởng và giới hạn nghiệm thu.


## Ghi chú phiên bản v1.7

Xem `RELEASE_v1.7_LONG_VUONG.md` và `V17_QA_ACCEPTANCE_REPORT.md` để biết các thay đổi hiệu ứng Long Vương, kiểm thử đã chạy và giới hạn nghiệm thu. Bản này chưa được xác minh trên Supabase staging hoặc Render production.
