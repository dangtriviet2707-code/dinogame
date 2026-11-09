# Viet Legends v1.7.10 – Long Vương Lobby Gear Animation

## Thay đổi
- Sảnh phản ánh riêng từng món Long Vương đang được trang bị: mũ, áo, quần và giày.
- Hiển thị lớp hình SVG của từng món trên nhân vật sảnh; không cần mặc đủ bộ mới thấy thay đổi.
- Khi mặc đủ bốn món, bật áo choàng xanh, hào quang và nhịp phát sáng nhẹ.
- Giữ hoạt ảnh idle của nhân vật sảnh (nhún người, chuyển động đầu, tay, chân và chớp mắt).
- Làm mới ngoại hình sảnh ngay khi dữ liệu người chơi/trang bị được cập nhật, không cần đăng xuất hoặc tải lại trang.
- Không thay đổi ID, chỉ số, kỹ năng, sát thương hay cơ chế trang bị.

## Kiểm tra
- JavaScript inline được trích xuất và kiểm tra cú pháp bằng `node --check`.
- Đã kiểm tra các hook lớp CSS và đường dẫn bốn ảnh SVG Long Vương.
- Bộ pytest chưa chạy hết được trong môi trường đóng gói do thiếu dependency Flask (`ModuleNotFoundError: flask`); cần chạy lại sau `pip install -r requirements.txt`.
- Chưa kiểm thử trực quan trên trình duyệt/điện thoại.
