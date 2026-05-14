# CLAUDE.local.md — Private Config (KHÔNG commit file này)

## Facebook Credentials
Điền vào file `.env` (xem `.env.example`):
```
FB_EMAIL=your-email@example.com
FB_PASSWORD=your-password
```

## Cookie Session (nếu không muốn nhập password)
Lấy từ browser DevTools → Application → Cookies → facebook.com:
```
FB_COOKIE_C_USER=
FB_COOKIE_XS=
FB_COOKIE_DATR=
```

## Target Pages đang cào
```
# Thêm vào config.yaml > target_pages:
# - https://www.facebook.com/groups/YOUR_GROUP_ID
# - https://www.facebook.com/YOUR_PAGE_NAME
```

## Notes cá nhân
- Cookie thường hết hạn sau ~90 ngày
- Chạy `python src/main.py login` để refresh cookie
- Nếu bị checkpoint: đăng nhập thủ công trên browser rồi export cookie
