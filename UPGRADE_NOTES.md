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

## Bản vá Admin console, tên tài khoản ở nhà chính, khủng long bay (07/11/2026)

### Admin
Nguyên nhân gốc đã sửa:
- Ô `#cmd` có `z-index:9` nên bị sảnh (z20), màn chơi (z12) và thanh tác giả (z100) che mất. Nay là `#cmdBox` z-index 140, có vùng hiển thị kết quả.
- Sau khi nhập đúng mật khẩu, client chỉ đặt `isAdmin=true` mà không mở lại ô lệnh. Nay tự mở và focus ô lệnh.
- Regex tách lệnh viết nhầm thành `/\\s+/` (khớp dấu `\`), nên mọi lệnh có tham số đều báo "không tồn tại".
- `typing()` không tính hộp mật khẩu: gõ Q/E/R/F/Space/Enter vẫn kích hoạt game. Nay mọi `INPUT/TEXTAREA` và hộp mật khẩu đều chặn phím game.
- Giới hạn "sai quá 5 lần" dùng `remote_addr`; sau proxy Render mọi người cùng một IP. Đã thêm `ProxyFix` (X-Forwarded-For).
- `#toast` z-index 9 bị sảnh che, nên thông báo không thấy ở nhà chính. Nay z-index 150.

Lệnh Admin giờ chạy ở server: `POST /api/admin/command` (kiểm quyền, kiểm tham số, trả `message`/`error` rõ ràng; trạng thái cheat lưu trong session). Lệnh: `/help /speed n|auto /god on|off /jump n /fire on|off /fly on|off /grant <tên> <itemId...> /whoami /status /off`.
- Xác thực Admin chỉ đặt `session["admin"]`; không đổi `session["key"]` (không chuyển tài khoản).
- Đăng nhập tài khoản khác giữ quyền Admin của phiên; Đăng xuất xoá cả hai. Mọi phản hồi login/register/me đều kèm `admin` + `cheat` để client đồng bộ.
- Trong ván chơi, lệnh thành công sẽ đóng console và hiện toast để phím điều khiển trở lại game.

### Nhà chính
- Bảng tên ngay dưới nhân vật (`#homePetName`, `#homePetSub`) lấy từ `me.name` (player trong session), kèm Lv/hạng. Khách hiển thị "Khách phiêu lưu".
- `renderHomeIdentity()` chạy trong `setMe()` và `enterLobby()`, nên đổi tài khoản/reload/relogin luôn đúng tên.
- Thêm nút "Đổi tài khoản" (đăng xuất rồi về màn đăng nhập). `_public()` dùng `rec.get("name") or key` để bản ghi legacy thiếu `name` không gây lỗi 500; leaderboard cũng vậy.

### Khủng long bay (phím E, mở sau Linh Khuyển)
- Thay hẳn mô hình vẽ: `drawFlyer()` vẽ khủng long bay (đầu mỏ dài, mào, đuôi bánh lái, chân co, hai cánh màng có xương/ngón) thay cho khủng long đứng. Màu thân theo cấp tiến hóa; phụ kiện (mào vàng, giáp lưng, lửa đuôi) theo cấp.
- Animation: cánh vỗ theo pha (cánh xa lệch pha), đầu cánh trễ pha, vỗ nhanh khi bay lên và chậm khi lượn xuống, thân nghiêng theo hướng bay, miệng mở khi phun lửa/hắc ám, bóng đổ co giãn theo độ cao, hiệu ứng chớp sáng + tia lửa khi biến hình/hết biến hình.
- Vật lý bay (`flyStep`): không trọng lực, không dính mặt đất. ↑/W/Space lên, ↓/S xuống, ←/→ hoặc A/D ngang; trên cảm ứng chạm/kéo để bay tới điểm chạm. Giới hạn trong khung chơi (trần y=100, sát đất y=226, x 14–680).
- Hitbox riêng cho dạng bay; lửa/hắc ám bắn từ miệng.
- Hết giờ (30s) hoặc chết/về nhà: `endTransform()` tắt cờ `P.flying`, xoá phím/điểm chạm, nhân vật rơi về đất và trở lại vị trí x=60; kỹ năng vẫn hồi chiêu như cũ.
- Biến hình chỉ thay `P.*` (dạng/vị trí/animation). Không đụng `hp`, `maxHp`, `gearStats`, `me`, túi đồ hay điểm; đòn đánh khi bay vẫn trừ "mạng bay" như cũ.
- Khi đang bay: Né (Shift) và Độn thổ bị khoá để tránh xung đột trạng thái.

### Kiểm thử đã chạy
Flask test client (25 ca: quyền, tham số, session, giới hạn theo IP, bản ghi legacy) và Playwright/Chromium (70 ca: luồng Admin, đổi tài khoản/reload, bay/hạ cánh, toàn vẹn HP–trang bị, chết/thoát khi đang bay, giao diện điện thoại). Chưa kiểm thử với Supabase thật vì môi trường không có mạng.

## Hệ thống sprite nhân vật (9 bộ)
- Nhân vật: `player`, `boss_d`, `boss_c`, `boss_b`, `boss_a`, `boss_s`, `linh_khuyen`, `ma_nu`, `ma_than`.
- Mỗi nhân vật: `public/assets/characters/<id>.png` (PNG nền trong suốt), `<id>_sheet.png` (sprite sheet 6 hàng x 6 frame, khung 192x192: idle, walk, attack, skill, hurt, die). Từng frame PNG riêng nằm ở `assets_src/frames/<id>/`.
- Manifest: `public/assets/characters/sprites.json`, cũng được trả về trong `/api/config` (`characters`).
- Dựng lại toàn bộ từ ảnh tham chiếu: `python3 tools/build_sprites.py` (cần numpy, opencv-python, scipy).
- Trong `index.html`: `SPR`, `drawChar(id, anim, t, cx, footY, fitW, fitH, opts)`; nếu ảnh chưa tải, game tự dùng hình vẽ cũ.
