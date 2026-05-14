"""Parse HTML Facebook thành structured data. Chứa SELECTORS dict và helper parsers."""

import re
from datetime import datetime, timedelta
from typing import Optional

from utils.logger import setup_logger

logger = setup_logger(__name__)

# CSS Selectors — cập nhật khi Facebook thay đổi HTML
# Xem .claude/agents/researcher.md để biết cách tìm selector mới
# Mỗi key là list: thử từ đầu đến cuối, dùng cái đầu tiên tìm được element
SELECTORS: dict[str, list[str]] = {
    "post_container": [
        '[role="article"][aria-posinset]',          # Layout cũ
        '[role="feed"] > div [role="article"]',     # Layout mới (nested)
        '[role="article"]',                          # Fallback chung
    ],
    "post_content": [
        '[data-ad-preview="message"]',
        '[data-testid="post_message"]',
        'div[class*="userContent"]',
        '[role="article"] div[dir="auto"] > div > div',
        '[role="article"] div[dir="auto"]',
    ],
    "comment_item": [
        '[aria-label*="Bình luận"] > div',
        'div[role="article"] ul > li',
        'div[aria-label="Comment"]',
        '[data-testid="UFI2Comment/root_depth_0"]',
    ],
    "comment_author": [
        'a[role="link"] span[dir="auto"]',
        'h3 > span > a',
        'strong > a',
        'a[class*="profileLink"]',
    ],
}


def parse_reaction_count(text: str) -> int:
    """Parse số reactions từ các format của Facebook: "1,234", "1.2K", "2M".

    Args:
        text: Text chứa số (có thể có chữ K, M hoặc dấu phẩy)

    Returns:
        Số nguyên, 0 nếu không parse được
    """
    if not text:
        return 0

    text = text.strip().upper()

    try:
        if "K" in text:
            # Giữ dấu "." (thập phân), bỏ dấu "," (ngăn cách nghìn)
            num_str = text.split("K")[0].replace(",", "")
            return int(float(num_str) * 1_000)
        if "M" in text:
            num_str = text.split("M")[0].replace(",", "")
            return int(float(num_str) * 1_000_000)
        # Số thông thường: bỏ dấu "," (ngăn cách nghìn) rồi lấy số đầu tiên
        numbers = re.findall(r"\d+", text.replace(",", ""))
        return int(numbers[0]) if numbers else 0
    except (ValueError, IndexError):
        return 0


def parse_timestamp(text: str) -> Optional[datetime]:
    """Parse timestamp từ nhiều format của Facebook.

    Hỗ trợ:
    - Tương đối: "5 phút trước", "2 giờ trước", "3 ngày trước"
    - Tuyệt đối: "15/03/2024", "15/03/2024 14:30", ISO 8601

    Args:
        text: Chuỗi thời gian từ Facebook

    Returns:
        datetime object hoặc None nếu không parse được
    """
    if not text:
        return None

    text = text.strip()
    now = datetime.now()

    # Relative patterns (Tiếng Việt + English)
    relative_patterns: list[tuple[str, str]] = [
        (r"(\d+)\s*phút", "minutes"),
        (r"(\d+)\s*giờ", "hours"),
        (r"(\d+)\s*ngày", "days"),
        (r"(\d+)\s*tuần", "weeks"),
        (r"(\d+)\s*tháng", "months"),
        (r"(\d+)\s*năm", "years"),
        (r"(\d+)\s*minute", "minutes"),
        (r"(\d+)\s*hour", "hours"),
        (r"(\d+)\s*day", "days"),
        (r"(\d+)\s*week", "weeks"),
        (r"(\d+)\s*month", "months"),
        (r"(\d+)\s*year", "years"),
    ]

    for pattern, unit in relative_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount = int(match.group(1))
            delta_map: dict[str, timedelta] = {
                "minutes": timedelta(minutes=amount),
                "hours": timedelta(hours=amount),
                "days": timedelta(days=amount),
                "weeks": timedelta(weeks=amount),
                "months": timedelta(days=amount * 30),
                "years": timedelta(days=amount * 365),
            }
            return now - delta_map[unit]

    # "Hôm qua" / "Yesterday"
    if re.search(r"hôm qua|yesterday", text, re.IGNORECASE):
        return now - timedelta(days=1)

    # Absolute date formats
    formats: list[str] = [
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%d tháng %m năm %Y lúc %H:%M",
        "%d tháng %m năm %Y",
        "%B %d, %Y at %I:%M %p",
        "%B %d, %Y",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    logger.debug(f"Không parse được timestamp: {text!r}")
    return None


def extract_post_url(html: str) -> str:
    """Trích xuất URL bài viết từ HTML của một article element.

    Args:
        html: Inner HTML của post element

    Returns:
        URL đầy đủ (https://...) hoặc "" nếu không tìm được
    """
    patterns: list[str] = [
        r'href="(https://www\.facebook\.com/[^"]*?/posts/[^"?]*)',
        r'href="(https://www\.facebook\.com/permalink\.php\?[^"]*story_fbid=[^"]*)',
        r'href="(/[^"]*?/posts/\d+[^"]*)"',
        r'href="(/permalink\.php\?[^"]*story_fbid=[^"]*)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            url = match.group(1)
            if url.startswith("/"):
                url = f"https://www.facebook.com{url}"
            # Bỏ tracking params, giữ phần path chính
            return url.split("&__")[0].split("?fbclid")[0]
    return ""
