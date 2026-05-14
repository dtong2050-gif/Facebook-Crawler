# Memory — Facebook Scraper Project

## CSS Selectors (cập nhật khi FB thay đổi HTML)

| Element           | Selector đang dùng                     | Last verified | Notes                        |
|-------------------|----------------------------------------|---------------|------------------------------|
| Post container    | `[role="article"]`                     | -             | Fallback chain trong fb_parser |
| Post text         | `[data-ad-preview="message"]`          | -             | Thử nhiều selectors          |
| Post timestamp    | `a[role="link"] abbr`                  | -             | Có title attribute           |
| Reactions count   | `[aria-label*="reaction"]`             | -             | Parse text hoặc aria-label   |
| Comment list      | `[aria-label*="Bình luận"]`            | -             | Tiếng Việt                   |
| Load more btn     | `div[aria-label*="Xem thêm bình luận"]`| -             | -                            |

## Sessions lịch sử

| Date | Target | Posts | Comments | Notes |
|------|--------|-------|----------|-------|
| -    | -      | -     | -        | -     |

## Known Issues
- (chưa có)

## Decisions
- Dùng selector fallback chain thay vì 1 selector cứng → bền hơn khi FB update UI
- Block image/font requests trong Playwright → tăng tốc ~40%
- headless=False mặc định → ít bị detect hơn
