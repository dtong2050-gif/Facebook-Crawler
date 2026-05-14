# Workflow Rules

## Git Flow
- Branch từ `main` cho mỗi feature/fix
- Tên branch: `feat/login-ui`, `feat/crawl-api`, `fix/selector-update`, `chore/update-deps`
- Không commit trực tiếp vào `main`

## Commit Convention (Conventional Commits)
```
feat: thêm màn hình login với email/password
feat: thêm progress bar real-time cho crawl
fix: cập nhật selector bài viết sau FB UI update
fix: xử lý edge case Facebook yêu cầu OTP
chore: cập nhật requirements.txt
docs: thêm hướng dẫn deploy
refactor: tách crawl thread thành module riêng
test: thêm test cho excel exporter
```

## Phát triển local

```bash
pip install -r requirements.txt
playwright install chromium
python app.py
# Mở http://localhost:5000
```

Khi thay đổi `index.html` hoặc `app.py`: refresh browser là đủ (không cần restart nếu dùng `debug=True` trong dev).

## Checklist trước khi commit

- [ ] Không hardcode credentials trong bất kỳ file nào
- [ ] `index.html` hiển thị đúng trên Chrome/Edge (test thủ công)
- [ ] `/api/progress` trả về đúng format JSON
- [ ] Không có `print()` debug còn sót — chỉ dùng `logger`
- [ ] Threading lock được dùng đúng chỗ khi đọc/ghi `_state`
- [ ] Playwright errors được bắt và phản ánh về `_state["error"]`

## PR Process
1. Mô tả rõ: thay đổi UI/API gì, tại sao
2. Test thủ công luồng login → crawl → download trước khi tạo PR
3. Chạy `pytest tests/ -v` để kiểm tra exporter và parser

## Test thủ công UI (bắt buộc trước merge)

| Kịch bản | Kết quả mong đợi |
|----------|-----------------|
| Login sai mật khẩu | Hiện thông báo lỗi, không chuyển màn hình |
| Login đúng | Chuyển sang màn hình crawl |
| Nhập URL không hợp lệ | Hiện lỗi validate |
| Bắt đầu crawl | Progress bar tăng, log hiện ra |
| Crawl xong | Nút "Tải file Excel" xuất hiện |
| Click tải | Browser download file .xlsx |
| Refresh trang khi đang crawl | Progress tiếp tục (poll resume) |
