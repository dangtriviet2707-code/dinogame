# Khủng Long Tiến Hóa – DINO

Game chạy né vật cản kiểu khủng long T-Rex, viết bằng Python (Flask).

## Cài đặt và chạy

```bash
pip install -r requirements.txt
python app.py
```

Mở `http://localhost:4000`.

## Điều khiển

- Space / mũi tên lên: nhảy.
- Mũi tên xuống: cúi.
- Shift hoặc nút **NÉ**: lướt né nhanh, có hồi chiêu 2 giây và một khoảng miễn nhiễm ngắn.
- Giữ F hoặc giữ nút **PHUN LỬA**: bắn lửa khi đã nhặt bình lửa.
- Trên điện thoại: dùng các nút tròn NÉ và PHUN LỬA ở góc dưới bên phải; chạm màn chơi để nhảy/cúi.

## Boss

Boss tiêu chuẩn gồm hạng D, C, A, S; tiếp theo là ba Boss đặc biệt Linh Khuyển, Ma Nữ và Ma Thần. Mỗi Boss có tạo hình canvas riêng, màu sắc và hình dáng nhận diện khác nhau. Máy bay ném bom thả bom theo vị trí đã định, có dấu cảnh báo vùng rơi để người chơi chủ động né.

## Lưu điểm

Tài khoản và bảng xếp hạng được lưu qua API Flask trong `data/players.json`.

## Triển khai

### Render

Đặt Root Directory là `dino` nếu kho Git chứa thư mục dự án `dino/`; nếu đã đưa nội dung bên trong `dino/` lên thư mục gốc kho Git thì để Root Directory trống. Render có thể dùng `render.yaml` hoặc cấu hình thủ công:

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
- Health Check Path: `/`
- Tạo biến môi trường `SESSION_SECRET` bằng chuỗi bí mật ngẫu nhiên. `BASE_URL` đặt thành URL HTTPS của website sau khi deploy.

Nên chạy qua HTTPS và dùng máy chủ WSGI như Gunicorn khi triển khai công khai. File JSON phù hợp cho quy mô nhỏ; nhiều người chơi đồng thời nên chuyển sang SQLite hoặc cơ sở dữ liệu phù hợp.

## Cấu hình quản trị

Không phân phối file `.env` chứa mật khẩu. Nếu cần bật lệnh quản trị, sao chép `.env.example` thành `.env` trên máy triển khai và tự đặt `ADMIN_PASSWORD` cùng `SESSION_SECRET` riêng tư.
