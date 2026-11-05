# Khủng Long Tiến Hóa – DINO

Game chạy né vật cản kiểu khủng long T-Rex, viết bằng Python (Flask).

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

Lệnh quản trị ẩn vẫn được giữ nguyên: nhấn phím dấu huyền (`) hoặc bấm 5 lần vào dòng tác giả để mở ô lệnh, sau đó nhập:

```text
/admin MAT_KHAU_ADMIN
```

Đặt `ADMIN_PASSWORD` trong Environment Variables của Render. Không đặt mật khẩu trong mã nguồn, frontend, Git hoặc gửi mật khẩu qua chat. Sau khi xác thực, các lệnh `/help`, `/speed`, `/god`, `/jump`, `/fire`, `/off` hoạt động trong phiên đăng nhập.

## Thiết lập Supabase

1. Tạo project tại Supabase.
2. Mở **SQL Editor**, chạy toàn bộ nội dung file `supabase_schema.sql`.
3. Trong Supabase Project Settings -> API, lấy Project URL và `service_role` secret.
4. Trong Render -> dịch vụ DINO -> **Environment**, thêm:
   - `SUPABASE_URL`: Project URL.
   - `SUPABASE_SERVICE_ROLE_KEY`: service_role secret.
   - `SUPABASE_TABLE`: `dino_players`.
   - `ADMIN_PASSWORD`: mật khẩu Admin mới.
   - `SESSION_SECRET`: chuỗi bí mật ngẫu nhiên dài (Render có thể tự tạo).
   - `BASE_URL`: URL HTTPS của dịch vụ Render.
5. Deploy lại.

**Bảo mật:** `SUPABASE_SERVICE_ROLE_KEY` chỉ được lưu trong Environment Variables của Render. Tuyệt đối không đặt key này trong `public/index.html`, không commit vào Git và không chia sẻ công khai. Bảng bật Row Level Security và không cấp quyền cho `anon`/`authenticated`; backend Flask mới được ghi/đọc bằng service role.

## Chuyển dữ liệu cũ

Khi ứng dụng khởi động với Supabase đã cấu hình:
- Nếu bảng `dino_players` còn trống, server tự nhập toàn bộ tài khoản từ `data/players.json` một lần.
- Nếu bảng đã có dữ liệu, server không ghi đè bằng JSON cũ.
- Dữ liệu JSON vẫn được giữ làm snapshot dự phòng; khi Supabase bật, mọi lần đọc/ghi chính thức đều đi qua Supabase.
- Nếu Supabase lỗi, API trả lỗi thay vì báo lưu thành công giả.

Trước khi deploy, hãy giữ lại bản ZIP và sao lưu file `data/players.json` mới nhất từ máy chủ cũ nếu có dữ liệu phát sinh sau thời điểm tạo ZIP. Bản JSON trong ZIP chỉ chứa snapshot đi kèm gói nguồn.

## Triển khai Render

- Root Directory: `dino` nếu kho Git chứa thư mục `dino/`; nếu nội dung trong `dino/` đã nằm ở root thì để trống.
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
- Health Check Path: `/healthz`

Render free có thể spin down khi không hoạt động. Supabase giữ dữ liệu bền vững độc lập với filesystem tạm của Render.
