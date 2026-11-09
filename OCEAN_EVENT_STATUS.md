# Sự kiện Đại Dương – Long Vương: trạng thái tích hợp

## Source nền tảng
- Đầu vào thực tế: `DINO_MMRPG_v13.zip` (không phải v12 như ghi trong kế hoạch).
- Engine: Flask backend + game frontend HTML/CSS/JavaScript, gameplay vẽ bằng HTML5 Canvas.
- Lưu trữ: `data/players.json` local hoặc Supabase qua backend; dữ liệu người chơi được chuẩn hóa bằng `_defaults()`.
- Boss hiện hữu: 8 boss (D/C/B/A/S, Linh Khuyển, Ma Nữ, Ma Thần); hệ thống boss/đạn/va chạm nằm trong `public/index.html`.
- Trang bị hiện hữu: 4 slot helmet/armor/pants/boots; API equip/unequip và chỉ số được quản lý ở `app.py`.
- Biến hình hiện hữu: `startTransform()`, `endTransform()`, `flyStep()`, `drawFlyer()`; trước thay đổi là khủng long bay với cánh vỗ, không phải Thần Long thân dài.

## Đã thực hiện trong gói này
1. Tách 5 boss từ ảnh đầu thành 5 PNG riêng nền trong suốt:
   - `hai_yeu_co_dai.png`
   - `thuy_hau_tu.png`
   - `cuu_dau_hai_xa.png`
   - `hai_ma.png`
   - `long_vuong.png`
2. Tách ảnh tham chiếu trang bị đầy đủ và Thần Long thành PNG nền trong suốt:
   - `long_vuong_equipped.png`
   - `than_long_form.png`
3. Thêm dữ liệu 4 món Long Vương vào `GEAR_CATALOG`, dùng đúng 4 slot hiện có; không thay đổi schema trang bị cũ.
4. Bổ sung trường tương thích trong hồ sơ người chơi: tiến trình sự kiện, trạng thái hoàn thành/nhận thưởng và hai kỹ năng sự kiện.
5. Thêm API lưu tiến trình `/api/ocean/progress` và API nhận bộ thưởng `/api/ocean/claim`. API claim có cờ idempotent để không cấp trùng bộ trang bị khi gọi lại.
6. Thêm cấu hình sự kiện 5 boss vào `/api/config` (tên, HP, sát thương, phòng thủ, tốc độ, cooldown, đường dẫn ảnh).
7. Khi mặc đủ 4 món Long Vương, frontend hiển thị ảnh tham chiếu trang bị thay cho sprite nhân vật thường.
8. Khi tài khoản có quyền `oceanDragon`, trạng thái bay dùng ảnh Thần Long và biến dạng theo các dải ảnh để tạo chuyển động uốn lượn thay vì chỉ phóng to ảnh tĩnh.
9. Nâng cache service worker lên `dino-v10`.

## Chưa hoàn thành – không được xem là bản phát hành tính năng cuối
- Chưa tích hợp luồng gameplay thực tế của sự kiện 5 ải vào vòng lặp boss hiện tại.
- Chưa có xác suất kích hoạt 50% tại các mốc boss B/A/S/Linh Khuyển/Ma Nữ/Ma Thần.
- Chưa có cảnh chuyển tiếp “CƠN SÓNG LỚN ĐÃ ẬP TỚI”, hiệu ứng nuốt người chơi, tạm dừng và khôi phục đúng trận đang chơi.
- Chưa gắn AI, kỹ năng, sát thương và hitbox riêng của 5 boss đại dương vào hệ thống chiến đấu hiện tại.
- Chưa có màn hội thoại Long Vương và quy trình chỉ trao thưởng sau khi hội thoại kết thúc được nối với gameplay. API claim hiện kiểm tra cờ `dialogueComplete` từ client; cần bổ sung xác thực trạng thái sự kiện phía server trước khi phát hành công khai.
- Chưa triển khai kỹ năng tối thượng Nộ Hải Thần Phong trong gameplay.
- Chưa kiểm thử chuyển trạng thái biến hình khi đổi bản đồ, chết, đăng xuất, tháo trang bị hoặc tải lại giữa sự kiện.
- Hiệu ứng uốn lượn hiện tại là biến dạng dải ảnh 2D nhẹ, chưa phải rig đầu/thân/đuôi nhiều khớp hoặc sprite animation chuyên nghiệp.

## Kiểm tra đã chạy
- `python -m py_compile app.py`: đạt.
- `node --check` cho inline JavaScript trong `public/index.html`: đạt.
- Kiểm tra 7 PNG: đủ 5 boss + 2 ảnh tham chiếu; kênh alpha có nền trong suốt.
- Chưa chạy Flask test client / end-to-end vì môi trường đóng gói hiện tại không cài Flask và không có quyền truy cập package index.

## File chính được chỉnh sửa
- `app.py`: dữ liệu trang bị, cấu hình sự kiện, hồ sơ người chơi, API tiến trình và nhận thưởng.
- `public/index.html`: hiển thị bộ Long Vương và biến dạng hình ảnh Thần Long.
- `public/sw.js`: tăng phiên bản cache.
- `public/assets/ocean/*.png`: 7 tài nguyên đồ họa.


## Bản vá bảo mật bổ sung (v14 security patch)
- Đã vô hiệu hóa fail-closed `POST /api/ocean/progress`: client không còn được tự gửi `stage` để nâng tiến trình.
- Đã vô hiệu hóa fail-closed `POST /api/ocean/claim`: cờ `dialogueComplete` từ client không còn đủ điều kiện cấp thưởng.
- Hai endpoint trả HTTP 409 cho tài khoản đã đăng nhập cho đến khi gameplay phía server xác thực được các lần hạ boss, chuyển ải và kết thúc hội thoại.
- Đây là biện pháp chặn khai thác tạm thời, không phải triển khai gameplay hoặc cơ chế xác thực hoàn chỉnh. Phần thưởng hiện không thể nhận qua hai API này.

## Cập nhật v15 – Giai đoạn 1 (nền state machine)
- Bổ sung state machine server-side cho phiên 5 ải trong `app.py`.
- Trạng thái phiên và stage không được nhận từ request client; các chuyển trạng thái chỉ qua hàm nội bộ có capability object.
- Thêm `GET /api/ocean/progress` read-only. POST progress và claim vẫn fail-closed.
- Có test mới trong `tests/test_ocean_state_machine.py`; chưa thể chạy integration test ở môi trường build do thiếu Flask và không có mạng cài dependency.
- Chưa tích hợp combat server-authoritative, trigger sự kiện 50%, giao diện chuyển cảnh hoặc trao thưởng. Vì vậy v15 hiện là bản nền Giai đoạn 1 đang làm, chưa nghiệm thu hoàn tất.


## v15 – Cập nhật hoàn thiện nền quản lý phiên (2026-11-09)
- Bổ sung các wrapper server-only để bắt đầu phiên, xác nhận hạ boss và xác nhận hội thoại theo giao dịch có khóa; dữ liệu chỉ được báo thành công sau khi storage ghi thành công.
- GET progress khôi phục từ player record và ghi trạng thái EXPIRED khi phiên đã quá hạn.
- Sửa kiểm thử boss bị hạ trùng và thêm kiểm thử lưu trữ/lỗi ghi/hết hạn.
- Vẫn khóa API client mutation và claim. Combat resolver server-authoritative chưa có nên chưa thể nối gameplay thật hoặc mở nhận thưởng.

## v1.6 – Long Vương Complete (09/11/2026)
- Đã thêm `/api/ocean/encounter`: roll 50% tại server, kích hoạt từ các boss B/A/S/Linh Khuyển/Ma Nữ/Ma Thần sau khi vòng chơi client kết thúc boss; giới hạn 30 giây giữa các lần thử.
- Đã thêm combat theo lượt `/api/ocean/action`; server tự quản lý HP hai bên, sát thương, bạo kích, phòng thủ, hồi phục, số lượt và thứ tự 5 boss. Client không thể gửi HP/sát thương/kết quả hạ boss.
- Có eventId + turn sequence để từ chối request cũ / request trùng; trạng thái battle lưu trong player record.
- Đã thêm hội thoại 3 bước, endpoint hoàn tất từng bước và claim 4 vật phẩm idempotent; mở khóa `oceanDragon` và `oceanUltimate`.
- Thêm UI sự kiện tại sảnh, hình Boss, nút chiến đấu, hội thoại và nhận thưởng; thêm nút/phím G cho Nộ Hải Thần Phong trong runner và cho phép biến hình Thần Long.
- Kiểm tra cú pháp Python và JavaScript đạt. 10 test logic state machine chạy qua test harness có shim vì môi trường thiếu Flask/Werkzeug; route integration và browser E2E chưa được chạy.
- Giới hạn còn lại: trigger roll bắt nguồn từ client runner nên client có thể tự gọi endpoint để thử roll; điều này không thể vượt qua combat/claim server-side. Muốn xác minh cả boss thường phải chuyển runner cũ sang combat server-authoritative. Duy trì 1 Gunicorn worker cho tới khi có transaction phân tán.
