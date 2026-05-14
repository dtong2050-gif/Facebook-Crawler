# Facebook Scraper

Cào bài viết và comments từ Facebook Page/Group, export ra file Excel (`.xlsx`).

## Tech Stack

| Thư viện | Dùng cho |
|----------|----------|
| **Playwright** | Điều khiển Chrome thật, tránh bị detect bot |
| **openpyxl** | Ghi file Excel, không cần pandas |
| **rich** | CLI progress bar, colored logs |
| **python-dotenv** | Load `.env` |
| **pyyaml** | Load `config.yaml` |

## Cài đặt

```bash
# 1. Clone repo
git clone <repo-url>
cd fb-scraper

# 2. Cài Python dependencies (cần Python 3.11+)
pip install -r requirements.txt

# 3. Cài Playwright browsers
playwright install chromium

# 4. Tạo file .env từ template
cp .env.example .env
# Mở .env và điền FB_EMAIL, FB_PASSWORD
```

## Cách dùng

### Bước 1: Đăng nhập

```bash
python src/main.py login
```

Cửa sổ Chrome sẽ mở. Đăng nhập vào Facebook. Cookie được lưu tự động vào `cookies/fb_cookies.json`.

### Bước 2: Cấu hình target pages

Sửa `config.yaml`:

```yaml
target_pages:
  - https://www.facebook.com/groups/YOUR_GROUP_ID
  - https://www.facebook.com/YOUR_PAGE_NAME
```

### Bước 3: Cào dữ liệu

```bash
# Cào theo config.yaml
python src/main.py scrape

# Giới hạn số bài
python src/main.py scrape --max-posts 50

# Chạy thử nhanh với 5 bài đầu
python src/main.py test
```

## Output

File Excel trong `data/`:

```
data/crawl_2024-03-15_14-30_group_12345.xlsx
```

**Sheet Posts:**
| STT | Post_ID | Content | Reactions | Comments_Count | Shares | Posted_At | Scraped_At | URL |

**Sheet Comments:**
| STT | Post_ID | Author | Content | Reactions | Reply_To | Commented_At | Scraped_At |

## Cấu hình (`config.yaml`)

| Key | Default | Mô tả |
|-----|---------|-------|
| `scroll_times` | 10 | Số lần scroll để load thêm bài |
| `delay_min/max` | 2.0 / 5.0 | Delay ngẫu nhiên giữa actions (giây) |
| `max_posts_per_page` | 100 | Giới hạn số bài mỗi page |
| `include_comments` | true | Có cào comments không |
| `headless` | false | `false` = hiện Chrome (khuyến nghị) |

## Chạy tests

```bash
pytest tests/ -v
```

## Xử lý lỗi thường gặp

| Lỗi | Nguyên nhân | Giải pháp |
|-----|-------------|-----------|
| `LoginError` | Cookie hết hạn | Chạy `python src/main.py login` lại |
| Posts trống | Facebook thay HTML | Xem `.claude/agents/researcher.md` |
| `RateLimitError` | Cào quá nhanh | Tăng `delay_min/max` trong `config.yaml` |
| `TimeoutError` | Mạng chậm hoặc bị block | Tăng timeout, thử lại sau |

## Lưu ý quan trọng

- **Không dùng `headless: true`** trong production — Facebook dễ detect và block
- Cookie hết hạn sau ~90 ngày, cần login lại
- Nếu bị checkpoint: đăng nhập thủ công trên Chrome rồi export cookie
- Tuân thủ [Facebook Terms of Service](https://www.facebook.com/terms.php) khi sử dụng tool này
