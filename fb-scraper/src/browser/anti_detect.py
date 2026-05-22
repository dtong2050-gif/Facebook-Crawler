"""Anti-detection: random delays, natural scroll, user-agent pool."""

import asyncio
import random
from typing import Optional

from playwright.async_api import Page

from utils.logger import setup_logger

logger = setup_logger(__name__)

DESKTOP_USER_AGENTS: list[str] = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
]


# Hệ số nhân áp dụng cho toàn bộ delay (chậm/bình thường/nhanh). Đặt qua
# set_delay_multiplier() trước khi crawl bắt đầu.
_DELAY_MULT: float = 1.0


def set_delay_multiplier(mult: float) -> None:
    """Đặt hệ số nhân cho random_delay (clamp [0.2, 5.0])."""
    global _DELAY_MULT
    _DELAY_MULT = max(0.2, min(5.0, float(mult)))


def get_delay_multiplier() -> float:
    """Lấy hệ số nhân hiện tại — dùng để scale các asyncio.sleep ngoài random_delay."""
    return _DELAY_MULT


async def random_delay(min_seconds: float = 2.0, max_seconds: float = 5.0) -> None:
    """Delay ngẫu nhiên giữa các action để tránh bị detect.

    Args:
        min_seconds: Thời gian tối thiểu (giây)
        max_seconds: Thời gian tối đa (giây)
    """
    delay = random.uniform(min_seconds, max_seconds) * _DELAY_MULT
    logger.debug(f"Delay {delay:.2f}s (mult={_DELAY_MULT:.2f})")
    await asyncio.sleep(delay)


async def natural_scroll(
    page: Page,
    distance: Optional[int] = None,
    direction: str = "down",
) -> None:
    """Scroll tự nhiên, chia thành nhiều bước nhỏ.

    Args:
        page: Playwright Page object
        distance: Khoảng cách scroll (pixel). None = random 400–900px
        direction: "down" hoặc "up"
    """
    if distance is None:
        distance = random.randint(700, 1400)

    if direction == "up":
        distance = -distance

    steps = random.randint(4, 10)
    per_step = distance // steps

    for _ in range(steps):
        await page.mouse.wheel(0, per_step)
        await asyncio.sleep(random.uniform(0.04, 0.18))


async def random_mouse_move(page: Page) -> None:
    """Di chuyển chuột ngẫu nhiên để giả lập người dùng.

    Args:
        page: Playwright Page object
    """
    viewport = page.viewport_size
    if viewport is None:
        return

    x = random.randint(80, viewport["width"] - 80)
    y = random.randint(80, viewport["height"] - 80)
    await page.mouse.move(x, y)
    await asyncio.sleep(random.uniform(0.1, 0.3))


def get_random_user_agent(mobile: bool = False) -> str:
    """Lấy một user-agent ngẫu nhiên từ pool.

    Args:
        mobile: True để lấy mobile UA (chưa implement, fallback về desktop)

    Returns:
        User-agent string
    """
    return random.choice(DESKTOP_USER_AGENTS)
