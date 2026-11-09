# VIET LEGENDS v1.7.5 – LONG VƯƠNG TRANSFORM EQUIPMENT GATE

## Sửa đổi
- Biến hình Thần Long (kỹ năng `oceanDragon`) chỉ hoạt động khi nhân vật đang mặc đủ 4 món trang bị Long Vương: mũ, áo, quần và giày.
- Nút biến hình không được mở chỉ vì tài khoản đã sở hữu kỹ năng Thần Long; cần thỏa điều kiện mặc đủ bộ.
- Khi không mặc đủ bộ Long Vương, nhân vật không hiển thị hình dạng Thần Long.
- Kỹ năng biến hình thông thường (`transform`) và điều kiện mở khóa cũ vẫn được giữ độc lập.
- Giữ nguyên các tệp, tài nguyên, bản đồ, dữ liệu cấu hình và chức năng khác của gói nguồn.

## Kiểm tra
- JavaScript nội tuyến trong `public/index.html` đã được kiểm tra cú pháp bằng Node.js (`node --check`).
