"""Cào bài viết từ Facebook Page/Group bằng cách scroll feed."""

from typing import Optional

from playwright.async_api import Page
from rich.progress import Progress, TaskID

from browser.anti_detect import natural_scroll, random_delay
from config import Config
from scrapers.base import BaseScraper, PostData, RateLimitError, ScraperError
from utils.helpers import clean_text, extract_post_id
from utils.logger import setup_logger

logger = setup_logger(__name__)

_BLOCKED_URL_PATTERNS: list[str] = ["checkpoint", "security_check", "login", "disabled"]

# JS chạy trong browser để extract tất cả posts trong DOM hiện tại.
# Trả về list of { url, storyId, author, content } cho mỗi article.
_JS_EXTRACT_ALL_POSTS = r"""
() => {
  const txt = (el) => el ? (el.textContent || '').trim() : '';

  // Thử selector theo thứ tự ưu tiên
  let articles = Array.from(document.querySelectorAll('[role="article"][aria-posinset]'));
  if (articles.length === 0) {
    articles = Array.from(document.querySelectorAll('[role="feed"] [role="article"]'));
  }
  if (articles.length === 0) {
    articles = Array.from(document.querySelectorAll('[role="article"]')).filter(a =>
      a.querySelector('a[href*="/posts/"], a[href*="story_fbid"], a[href*="permalink/"]')
    );
  }

  const results = [];
  for (const a of articles) {
    try {
      // URL bài viết
      const link = a.querySelector('a[href*="/posts/"], a[href*="story_fbid"], a[href*="permalink/"]');
      let url = link ? link.href : '';
      if (url) {
        url = url.split('?fbclid')[0].split('&__')[0];
      }

      const storyId = a.getAttribute('data-story-id') || '';

      // Tác giả: h2/h3/h4 có link
      let author = '';
      const heading = a.querySelector('h2, h3, h4');
      if (heading) {
        const aLink = heading.querySelector('a[role="link"]');
        author = (aLink ? aLink.innerText : heading.innerText).split('\n')[0].trim();
      }

      // Nội dung: ưu tiên data-ad-preview="message", fallback longest dir=auto
      let content = '';
      const msg = a.querySelector('[data-ad-preview="message"], [data-testid="post_message"]');
      if (msg) {
        content = txt(msg);
      }
      if (!content) {
        for (const el of a.querySelectorAll('[dir="auto"]')) {
          const t = txt(el);
          if (t.length > content.length) content = t;
        }
      }

      // Số bình luận từ feed — dùng để bỏ qua bài không có comment ở Phase 2
      // -1 = không xác định được (vẫn sẽ cào), 0 = chắc chắn không có comment
      // Lưu ý: FB thường KHÔNG hiện "0 bình luận" — bài không comment sẽ ra -1
      let commentCount = -1;
      const parseNum = (s) => {
        s = s.replace(/\./g, '').replace(/,/g, '');
        const k = /k/i.test(s), mil = /m/i.test(s);
        let n = parseFloat(s.replace(/[^\d.]/g, '')) || 0;
        if (k) n *= 1000; if (mil) n *= 1000000;
        return Math.round(n);
      };
      const reCmt = /(\d[\d.,]*\s*[km]?)\s*(bình luận|comment)/i;
      // Thử aria-label trước (đáng tin cậy nhất)
      for (const el of a.querySelectorAll('[aria-label]')) {
        const m = (el.getAttribute('aria-label') || '').match(reCmt);
        if (m) { commentCount = parseNum(m[1]); break; }
      }
      // Fallback: text của span/a/div[role=button] nhỏ gọn
      if (commentCount === -1) {
        for (const el of a.querySelectorAll('span, a, div[role="button"]')) {
          const t = (el.textContent || '').trim();
          if (t.length > 40) continue;
          const m = t.match(reCmt);
          if (m) { commentCount = parseNum(m[1]); break; }
        }
      }

      results.push({ url, storyId, author, content, commentCount });
    } catch (e) {}
  }
  return results;
}
"""


class PostScraper(BaseScraper):
    """Scroll feed Facebook và extract PostData từ mỗi article."""

    def __init__(self, config: Config) -> None:
        """Khởi tạo với config.

        Args:
            config: Config object
        """
        self.config = config

    async def scrape(
        self,
        page: Page,
        url: str,
        max_posts: int,
        progress: Optional[Progress] = None,
        task_id: Optional[TaskID] = None,
    ) -> list[PostData]:
        """Cào bài viết từ URL Facebook Page/Group.

        Args:
            page: Playwright Page object (đã load cookies)
            url: URL của Facebook Page/Group
            max_posts: Số bài tối đa cần cào
            progress: Rich Progress object (hiển thị progress bar)
            task_id: ID của task trong progress bar

        Returns:
            List PostData, giới hạn max_posts items

        Raises:
            ScraperError: Không thể navigate đến URL
            RateLimitError: Bị Facebook block hoặc redirect về checkpoint
        """
        logger.info(f"Bắt đầu cào posts: {url} (max={max_posts})")

        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
        except Exception as e:
            raise ScraperError(f"Không thể navigate đến {url}: {e}") from e

        await random_delay(2, 4)

        if self._is_blocked(page.url):
            raise RateLimitError(
                f"Bị redirect về trang block/checkpoint: {page.url}"
            )

        posts: list[PostData] = []
        seen_ids: set[str] = set()

        for scroll_num in range(self.config.scroll_times):
            new_posts = await self._extract_posts_from_page(page)

            for post in new_posts:
                if post.post_id not in seen_ids:
                    seen_ids.add(post.post_id)
                    posts.append(post)
                    if progress and task_id is not None:
                        progress.update(task_id, completed=min(len(posts), max_posts))
                    if len(posts) >= max_posts:
                        break

            if len(posts) >= max_posts:
                break

            logger.debug(f"Scroll {scroll_num + 1}/{self.config.scroll_times}: {len(posts)} posts")
            await natural_scroll(page)
            await random_delay(self.config.delay_min, self.config.delay_max)

        result = self.validate(posts)[:max_posts]
        logger.info(f"Cào xong: {len(result)} bài viết từ {url}")
        return result

    async def _extract_posts_from_page(self, page: Page) -> list[PostData]:
        """Trích xuất tất cả post articles bằng 1 lần evaluate() trong browser.

        Cách cũ tốn ~7 round-trip Playwright cho mỗi article. Cách mới gom hết
        vào 1 lệnh JS chạy trực tiếp trong browser → giảm thời gian extract từ
        ~15-20s xuống <1s.

        Args:
            page: Playwright Page object

        Returns:
            List PostData (chưa dedup)
        """
        try:
            raw = await page.evaluate(_JS_EXTRACT_ALL_POSTS)
        except Exception as e:
            logger.warning(f"Lỗi evaluate JS extract: {e}")
            return []

        if not raw:
            return []

        posts: list[PostData] = []
        for item in raw:
            url = item.get("url", "")
            post_id = extract_post_id(url) if url else ""
            if not post_id:
                post_id = item.get("storyId", "") or ""
            if not post_id:
                continue
            posts.append(PostData(
                post_id=post_id,
                url=url,
                author=clean_text(item.get("author", "") or ""),
                content=clean_text(item.get("content", "") or ""),
                comment_count=int(item.get("commentCount") or -1),
            ))
        return posts

    @staticmethod
    def _is_blocked(url: str) -> bool:
        """Kiểm tra URL có phải trang block/checkpoint không.

        Args:
            url: URL hiện tại của page

        Returns:
            True nếu bị redirect về trang không mong muốn
        """
        return any(pattern in url for pattern in _BLOCKED_URL_PATTERNS)
