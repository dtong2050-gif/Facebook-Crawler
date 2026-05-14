"""Cào comments và replies từ bài viết Facebook."""

from typing import Optional

from playwright.async_api import ElementHandle, Page

from browser.anti_detect import random_delay
from config import Config
from parsers.fb_parser import SELECTORS
from scrapers.base import BaseScraper, CommentData
from utils.helpers import clean_text
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Selectors cho nút "Xem thêm bình luận"
_LOAD_MORE_SELECTORS: list[str] = [
    'div[aria-label*="Xem thêm bình luận"]',
    'div[aria-label*="View more comments"]',
    'span[aria-label*="Xem thêm"]',
    '[role="button"][tabindex="0"]:has-text("Xem thêm")',
    '[role="button"][tabindex="0"]:has-text("View more")',
]


class CommentScraper(BaseScraper):
    """Mở rộng và cào comments/replies từ 1 bài viết Facebook."""

    def __init__(self, config: Config) -> None:
        """Khởi tạo với config.

        Args:
            config: Config object
        """
        self.config = config

    async def scrape(
        self,
        page: Page,
        post_url: str,
        post_id: str,
        max_comments: int = 500,
    ) -> list[CommentData]:
        """Cào tất cả comments của 1 bài viết.

        Args:
            page: Playwright Page object (đã login)
            post_url: URL bài viết
            post_id: ID bài viết (gắn vào từng CommentData)
            max_comments: Số comments tối đa

        Returns:
            List CommentData (đã validate)
        """
        if not post_url:
            logger.debug(f"Post {post_id}: không có URL, bỏ qua cào comments")
            return []

        logger.debug(f"Cào comments post {post_id}")

        try:
            await page.goto(post_url, wait_until="domcontentloaded", timeout=30_000)
            await random_delay(0.8, 1.5)
        except Exception as e:
            logger.warning(f"Không navigate đến post {post_id}: {e}")
            return []

        await self._expand_comments(page)
        comments = await self._extract_comments(page, post_id)
        result = self.validate(comments)[:max_comments]
        logger.debug(f"Post {post_id}: {len(result)} comments")
        return result

    async def _expand_comments(self, page: Page, max_clicks: int = 3) -> None:
        """Click "Xem thêm bình luận" để load thêm comments.

        Args:
            page: Playwright Page object
            max_clicks: Số lần click tối đa (giữ thấp để tránh crawl quá chậm)
        """
        for click_num in range(max_clicks):
            clicked = False
            for selector in _LOAD_MORE_SELECTORS:
                try:
                    btn = await page.query_selector(selector)
                    if btn:
                        await btn.scroll_into_view_if_needed()
                        await btn.click()
                        await random_delay(0.5, 1.0)
                        clicked = True
                        logger.debug(f"Clicked 'load more comments' ({click_num + 1})")
                        break
                except Exception:
                    continue

            if not clicked:
                break

    async def _extract_comments(self, page: Page, post_id: str) -> list[CommentData]:
        """Trích xuất tất cả comment elements từ page hiện tại.

        Args:
            page: Playwright Page object
            post_id: ID bài viết

        Returns:
            List CommentData (chưa validate)
        """
        comment_elements: Optional[list[ElementHandle]] = None

        for selector in SELECTORS["comment_item"]:
            try:
                found = await page.query_selector_all(selector)
                if found:
                    logger.debug(f"Comment selector: {selector!r} → {len(found)}")
                    comment_elements = found
                    break
            except Exception:
                continue

        if not comment_elements:
            logger.debug(f"Không tìm thấy comment elements cho post {post_id}")
            return []

        comments: list[CommentData] = []
        for el in comment_elements:
            try:
                comment = await self._parse_comment(el, post_id)
                if comment:
                    comments.append(comment)
            except Exception as e:
                logger.debug(f"Lỗi parse comment: {e}")
                continue

        return comments

    async def _parse_comment(
        self, element: ElementHandle, post_id: str
    ) -> Optional[CommentData]:
        """Parse 1 comment ElementHandle thành CommentData."""
        # Author — CSS selector fallback chain
        author = ""
        for selector in SELECTORS["comment_author"]:
            try:
                el = await element.query_selector(selector)
                if el:
                    raw = await el.inner_text()
                    author = clean_text(raw)
                    if author:
                        break
            except Exception:
                continue

        if not author:
            return None

        # Content — dùng JS để tránh selector bị phá vỡ bởi FB DOM update
        # Tìm div[dir="auto"] đầu tiên KHÔNG chứa link tác giả
        content = ""
        try:
            content = await element.evaluate("""el => {
                const divs = el.querySelectorAll('div[dir="auto"]');
                for (const div of divs) {
                    if (div.querySelector('a[role="link"]')) continue;
                    const text = (div.innerText || '').trim();
                    if (text && text.length > 1) return text;
                }
                // fallback: span[dir="auto"]
                const spans = el.querySelectorAll('span[dir="auto"]');
                for (const span of spans) {
                    if (span.querySelector('a')) continue;
                    const text = (span.innerText || '').trim();
                    if (text && text.length > 1) return text;
                }
                return '';
            }""")
            content = clean_text(content or "")
        except Exception:
            pass

        return CommentData(post_id=post_id, author=author, content=content)
