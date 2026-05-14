# Facebook Scraper — Project Brain

## Tổng quan
Ứng dụng web cào dữ liệu Facebook (bài viết + comments). Người dùng tương tác qua **trình duyệt web**:
1. Nhập email + mật khẩu Facebook → đăng nhập
2. Nhập URL group/page + số bài + số comment → bắt đầu cào
3. Theo dõi tiến trình real-time → tải file Excel khi xong

Backend dùng Flask phục vụ API + file tĩnh. Playwright chạy Chrome ẩn sau để thao tác Facebook.

## Luồng sử dụng

```
Mở http://localhost:5000
        │
        ▼
┌─────────────────────────┐
│  MÀNG HÌNH ĐĂNG NHẬP    │
│  ┌─────────────────┐    │
│  │ Email FB        │    │
│  ├─────────────────┤    │
│  │ Mật khẩu        │    │
│  └─────────────────┘    │
│  [  Đăng nhập  ]        │
└─────────────────────────┘
        │ POST /api/login (email, password)
        │ Playwright mở Chrome, đăng nhập thật
        ▼
┌─────────────────────────┐
│  MÀNG HÌNH CÀO DỮ LIỆU │
│  ┌─────────────────┐    │
│  │ URL Group/Page  │    │
│  ├─────────────────┤    │
│  │ Số bài viết     │    │
│  ├─────────────────┤    │
│  │ Số comments     │    │
│  └─────────────────┘    │
│  [ Bắt đầu cào ]        │
│  ─────────────────────  │
│  ████████░░ 60%         │  ← progress bar real-time
│  Posts: 45 | Cmts: 230  │  ← counter cập nhật liên tục
│  [logs hiển thị ở đây]  │  ← log stream
│  ─────────────────────  │
│  [ Tải file Excel ]     │  ← hiện ra khi xong
└─────────────────────────┘
```

## Tech Stack

| Layer | Thư viện | Ghi chú |
|-------|----------|---------|
| Web server | **Flask** | Serve API + index.html |
| Browser automation | **Playwright** | Chạy Chrome thật, async |
| Excel export | **openpyxl** | KHÔNG dùng pandas |
| Frontend | **Vanilla JS + HTML** | Không framework, không build step |
| Logging | **logging** (file) + stream tới UI | |

## Kiến trúc 3 lớp

```
app.py          — Flask server, REST API, quản lý global state (_crawler, _state)
src/            — Business logic (browser, scrapers, parsers, exporters, utils)
index.html      — SPA: 2 màn hình (login / crawl), poll /api/progress mỗi 2s
```

### REST API endpoints

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `POST` | `/api/login` | Nhận `{email, password}`, chạy Playwright login |
| `GET` | `/api/login/status` | Kiểm tra đã login chưa |
| `POST` | `/api/crawl` | Nhận `{url, max_posts, max_comments}`, bắt đầu crawl |
| `GET` | `/api/progress` | Trả về `{status, posts, comments, logs[], file_ready}` |
| `GET` | `/api/download` | Tải file Excel kết quả |
| `POST` | `/api/stop` | Dừng crawl đang chạy |

### Global state trong app.py

```python
_crawler: Optional[FacebookCrawler] = None   # singleton Playwright session
_state = {
    "status": "idle",          # idle | logging_in | crawling | done | error
    "posts": 0,
    "comments": 0,
    "logs": [],                # list string, tối đa 200 dòng
    "file_path": None,         # path khi xong
    "error": None,
}
_lock = threading.Lock()       # bảo vệ _state
```

Crawl chạy trong background `threading.Thread`; frontend poll `/api/progress` mỗi 2 giây.

## Cấu trúc file

```
app.py              — Flask entry point (PORT 5000)
index.html          — Toàn bộ UI (HTML + CSS + JS inline, dark theme)
src/
├── config.py       — Config dataclass (delays, limits, paths)
├── browser/
│   ├── session.py  — BrowserSession: launch, login, cookie
│   └── anti_detect.py — random delay, natural scroll
├── scrapers/
│   ├── base.py     — PostData, CommentData dataclasses
│   ├── post_scraper.py
│   └── comment_scraper.py
├── parsers/
│   └── fb_parser.py — SELECTORS dict, parse helpers
├── exporters/
│   └── excel_exporter.py — ghi .xlsx hai sheet
└── utils/
    ├── logger.py
    └── helpers.py
```

## Quy tắc quan trọng

### index.html
- **Một file duy nhất** — không tách CSS/JS riêng
- Hai trạng thái UI: `#login-screen` và `#crawl-screen`
- Khi login thành công → ẩn login screen, hiện crawl screen
- Poll `/api/progress` mỗi 2s khi đang crawl; dừng poll khi `status = done | error`
- Nút "Tải file Excel" chỉ hiện khi `file_ready = true`

### app.py
- `_crawler` là singleton — chỉ tạo 1 lần, tái sử dụng session
- Dùng `threading.Lock()` để bảo vệ `_state` khỏi race condition
- Login chạy sync trong request handler (không background thread)
- Crawl chạy trong background thread; cập nhật `_state` sau mỗi bài viết
- `app.run(host="0.0.0.0", port=5000, debug=False)`

### Không có .env hay config.yaml cho credentials
Thông tin đăng nhập được nhập **trực tiếp qua UI**, không lưu vào file. Cookie được lưu vào
`cookies/fb_cookies.json` sau khi login thành công để tái sử dụng session.

## Chạy app

```bash
pip install -r requirements.txt
playwright install chromium
python app.py
# Mở http://localhost:5000
```

## Output
File Excel trong `data/`: `crawl_YYYY-MM-DD_HH-MM_{page_name}.xlsx`
- Sheet **Posts**: STT, Post_ID, Content, Reactions, Comments_Count, Shares, Posted_At, Scraped_At, URL
- Sheet **Comments**: STT, Post_ID, Author, Content, Reactions, Reply_To, Commented_At, Scraped_At
