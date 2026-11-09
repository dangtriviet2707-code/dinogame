# VIET LEGENDS v1.7.4 – LONG VƯƠNG REAL-TIME EVENT

## Thay đổi
- Sảnh chỉ giới thiệu sự kiện; không còn nút thử vận may/bắt đầu thủ công.
- Sự kiện được kiểm tra ngẫu nhiên 50% sau khi hạ Boss đủ điều kiện trong màn chơi (B/A/S, Linh Khuyển, Ma Nữ, Ma Thần).
- Khi kích hoạt, người chơi vào đấu trường Đại Dương thời gian thực trên một bản đồ duy nhất.
- Năm Boss xuất hiện lần lượt: Hải Yêu Cổ Đại, Thủy Hầu Tử, Cửu Đầu Hải Xà, Hải Ma, Long Vương.
- Điều khiển: A/D hoặc phím mũi tên để di chuyển; Space để nhảy; J để đánh; Shift để lướt. Có nút cảm ứng cho điện thoại.
- Tiến trình Boss, thứ tự Boss, thất bại và hoàn thành được lưu qua API server.
- Giữ nguyên tài khoản, kho đồ, trang bị, nhiệm vụ, Admin, Supabase và tài nguyên cũ.

## Kiểm thử
- Cần chạy staging Render + Supabase để xác nhận persistence, đa tài khoản và trình duyệt mobile.
- Combat realtime diễn ra trên client; endpoint server xác nhận eventId và thứ tự Boss, nhưng chưa có server-side hitbox/physics validation chống cheat. Không dùng làm PvP/cạnh tranh có thưởng giá trị cho đến khi chuyển combat simulation lên server.
