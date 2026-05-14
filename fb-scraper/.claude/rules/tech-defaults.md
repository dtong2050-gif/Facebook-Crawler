# Tech Defaults

## Web Framework
- **Flask** — server web + REST API + serve static file `index.html`
- `app.run(host="0.0.0.0", port=5000, debug=False)`
- KHÔNG dùng FastAPI, Django, hay bất kỳ framework khác
- KHÔNG dùng Jinja2 template — index.html là file tĩnh thuần

## Frontend
- **Vanilla JS + HTML + CSS inline** trong 1 file `index.html` duy nhất
- KHÔNG dùng React, Vue, Angular hay bất kỳ JS framework nào
- KHÔNG có build step (npm, webpack, vite...)
- Dark theme, responsive đơn giản
- Poll `/api/progress` mỗi 2 giây bằng `setInterval` khi đang crawl
- Dừng poll khi nhận `status = "done"` hoặc `"error"`

## Concurrency Model
- **Login**: chạy sync trong request handler (blocking OK vì chỉ 1 user)
- **Crawl**: chạy trong `threading.Thread` để không block Flask
- **State**: `threading.Lock()` bảo vệ dict `_state` dùng chung
- Playwright chạy trong background thread → dùng `asyncio.run()` trong thread đó
- KHÔNG dùng `asyncio` ở tầng Flask (Flask là sync)

## Browser Automation
- **Playwright** — KHÔNG dùng Selenium, KHÔNG dùng requests/BeautifulSoup
- Chạy Chromium, `headless=True` trong production (không cần hiện Chrome khi có web UI)
- Disable ảnh/font để tăng tốc: `await page.route("**/*.{png,jpg,gif,webp,woff,woff2}", ...)`
- Luôn dùng async API: `async_playwright()` trong thread riêng

## Excel Export
- **openpyxl** — KHÔNG dùng pandas, KHÔNG dùng xlwt/xlrd
- Ghi trực tiếp từng row, không load template
- Auto-adjust column width, freeze header, auto-filter
- Tách sheet nếu > 50,000 rows

## Logging & Progress
- Log ra file: `logging.handlers.RotatingFileHandler` (10MB, 5 backups)
- Log stream tới UI: append vào `_state["logs"]` (tối đa 200 dòng), frontend lấy qua `/api/progress`
- Cập nhật `_state["posts"]` và `_state["comments"]` sau mỗi bài/comment xong
- KHÔNG log credentials (email, password, cookie values)

## Credentials
- **Nhập qua UI** (form login), KHÔNG lưu vào `.env` hay `config.yaml`
- Cookie lưu vào `cookies/fb_cookies.json` sau login thành công
- Khi khởi động lại app, check cookie cũ còn hợp lệ không → bỏ qua màn hình login nếu còn dùng được

## Config phi-credentials (config.yaml)
- `scraping.delay_min/max` — delay giữa actions
- `scraping.scroll_times` — số lần scroll
- `export.output_dir` — thư mục data/
- `browser.headless` — true/false
- Không có `target_pages`, `fb_email`, `fb_password` trong config.yaml

## Error Handling
- Login fail → trả về `{"success": false, "error": "..."}` qua API
- Crawl lỗi → cập nhật `_state["status"] = "error"`, `_state["error"] = message`
- Retry 3 lần với exponential backoff cho network errors
- Timeout: 30s cho `goto()`, 10s cho element wait

## Dependencies
```
flask>=3.0
playwright>=1.40
openpyxl>=3.1
pyyaml>=6.0
```

## KHÔNG dùng
- `pandas` — quá nặng chỉ để ghi Excel
- `selenium` — Playwright hiện đại hơn
- `requests` + `BeautifulSoup` — không render JS
- `python-dotenv` — credentials nhập qua UI, không cần .env
- `rich` / `argparse` — không còn CLI
- `scrapy` — overkill
