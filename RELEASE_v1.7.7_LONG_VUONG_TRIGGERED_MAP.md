# VIET LEGENDS v1.7.7 – LONG VƯƠNG KÍCH HOẠT NGẪU NHIÊN

## Thay đổi gameplay
- Giữ nguyên toàn bộ bản đồ thường và hệ thống Boss cũ trong lượt chơi bình thường.
- Sau khi hạ Boss đủ điều kiện (B, A, S, Linh Khuyển, Ma Nữ hoặc Ma Thần), máy chủ mới quay tỉ lệ kích hoạt sự kiện Long Vương.
- Chỉ khi sự kiện được kích hoạt, bản đồ hiện tại mới tạm chuyển sang bản đồ Đại Dương và Boss sự kiện xuất hiện lần lượt.
- Sự kiện dùng chung vòng lặp gameplay chính: di chuyển, nhảy, né, tấn công, HP, va chạm và kỹ năng; không mở một lối chơi riêng.
- Hoàn thành 5 Boss sẽ trở về đúng bản đồ cũ và tiếp tục lượt chơi đang dang dở; điểm, HP và tiến trình màn chơi không bị reset khi chuyển sự kiện.
- Mỗi ải Đại Dương dùng ảnh nền riêng tương ứng stage 1–5.
- Tăng phiên bản cache service worker để trình duyệt tải gameplay mới.

## Kiểm tra
- JavaScript nội tuyến: `node --check` thành công.
- Python backend: `py_compile` thành công.
- Kiểm tra giao diện Long Vương và tài nguyên: 9 tests passed.
- Bộ test state-machine backend chưa chạy được trong môi trường đóng gói vì thiếu dependency Flask.
