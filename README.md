# Khủng Long Hoàng Hôn

Game chạy né vật cản kiểu khủng long T-Rex của Chrome, viết bằng Python (Flask).
Dự án độc lập, không liên quan tới "Hầm Ngục Ba Tầng".

## Cài đặt và chạy

```
pip install -r requirements.txt
python app.py
```

Mở `http://localhost:4000`.

## Cách chơi

- Phím Cách hoặc mũi tên lên: nhảy
- Mũi tên xuống: cúi
- Trên điện thoại: chạm nửa trái màn hình để nhảy, nửa phải để cúi
- Chạy càng xa, tốc độ càng nhanh và hoàng hôn càng tối dần về đêm

## Lưu điểm

Bạn nhập một **biệt danh** (không cần mật khẩu) trước khi chơi. Điểm cao nhất
của biệt danh đó được lưu vào `data/players.json` và hiện trên bảng xếp hạng
top 10. Vì không có mật khẩu, ai gõ đúng tên nào thì điểm sẽ cộng vào tên đó —
phù hợp cho chơi vui, không phù hợp nếu cần chống giả mạo tên.

Muốn bảo vệ tên bằng mật khẩu (giống hệ thống tài khoản của game Hầm Ngục),
cứ nói để mình thêm vào.

## Trước khi đưa lên mạng

- Nên chạy qua HTTPS và dùng `gunicorn app:app` thay vì `python app.py`.
- File JSON phù hợp cho quy mô nhỏ; nhiều người chơi đồng thời nên chuyển
  sang SQLite hoặc cơ sở dữ liệu khác.
