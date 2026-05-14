"""Quản lý Playwright browser session: launch, login, cookie save/load."""

import json
import random
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from config import Config
from utils.logger import setup_logger

logger = setup_logger(__name__)


class LoginError(Exception):
    """Lỗi đăng nhập Facebook."""


class BrowserSession:
    """Async context manager cho Playwright browser session.

    Usage:
        async with BrowserSession(config) as session:
            page = await session.new_page()
            await session.load_cookies(page)
            ...
    """

    def __init__(self, config: Config) -> None:
        """Khởi tạo với config.

        Args:
            config: Config object chứa browser settings
        """
        self.config = config
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self) -> "BrowserSession":
        """Khởi động Playwright và mở browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--disable-extensions",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
        )
        # Ẩn dấu hiệu automation
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [{ name: 'Chrome PDF Plugin' }, { name: 'Chrome PDF Viewer' }]
            });
            window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {} };
        """)
        logger.info("Browser đã khởi động")
        return self

    async def __aexit__(self, *_: object) -> None:
        """Đóng context, browser và Playwright."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser đã đóng")

    async def new_page(self) -> Page:
        """Tạo page mới, block ảnh/font để tăng tốc.

        Returns:
            Page object sẵn sàng dùng
        """
        assert self._context is not None, "BrowserSession chưa được __aenter__"
        page = await self._context.new_page()
        # Block các resource không cần thiết
        await page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,eot}",
            lambda route: route.abort(),
        )
        return page

    async def login(self, page: Page, email: str, password: str) -> None:
        """Đăng nhập Facebook và chờ redirect thành công.

        Args:
            page: Playwright Page object
            email: Facebook email
            password: Facebook password

        Raises:
            LoginError: Nếu credentials rỗng hoặc đăng nhập thất bại
        """
        if not email or not password:
            raise LoginError("Email và mật khẩu không được để trống")

        logger.info("Đang điều hướng đến trang login...")
        await page.goto(
            "https://www.facebook.com/login",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        await page.wait_for_load_state("load", timeout=30_000)
        logger.info(f"URL sau goto: {page.url}")

        # Đã có cookies → FB redirect sang feed ngay
        if "facebook.com" in page.url and "/login" not in page.url and "checkpoint" not in page.url:
            logger.info("Đã có session, bỏ qua điền form")
            return

        # Gõ từng ký tự như người dùng thật (tránh bị phát hiện automation)
        async def _type_into(selectors: list[str], value: str, label: str) -> None:
            for sel in selectors:
                try:
                    el = await page.wait_for_selector(sel, state="visible", timeout=5_000)
                    if el is None:
                        continue
                    await el.click()
                    await page.wait_for_timeout(random.randint(200, 400))
                    await el.fill("")  # xóa giá trị cũ nếu có
                    await page.keyboard.type(value, delay=random.randint(40, 90))
                    return
                except Exception:
                    continue
            raise LoginError(f"Không tìm thấy ô {label}. URL: {page.url}")

        await _type_into(
            ["#email", 'input[name="email"]', 'input[type="email"]'],
            email, "email",
        )
        await page.wait_for_timeout(random.randint(500, 900))

        await _type_into(
            ["#pass", 'input[name="pass"]', 'input[type="password"]'],
            password, "mật khẩu",
        )
        await page.wait_for_timeout(random.randint(300, 600))

        # Submit form — thử nhiều cách
        _LOGIN_SELS = [
            'button[name="login"]',
            '[name="login"]',
            '#loginbutton',
            'button[type="submit"]',
            '[data-testid="royal_login_button"]',
            'input[type="submit"]',
        ]
        clicked = False
        for sel in _LOGIN_SELS:
            try:
                await page.click(sel, timeout=3_000)
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            # Fallback: nhấn Enter trên field password (luôn submit form)
            try:
                await page.keyboard.press("Enter")
                clicked = True
                logger.info("Dùng Enter để submit form đăng nhập")
            except Exception:
                pass

        if not clicked:
            raise LoginError(f"Không thể submit form đăng nhập. URL: {page.url}")

        # Không chờ redirect ở đây — _async_login trong app.py sẽ poll URL
        # và xử lý 2FA nếu cần
        logger.info("Đã click đăng nhập, đang chờ redirect...")

    async def save_cookies(self, page: Page) -> None:
        """Lưu cookies của context hiện tại ra file JSON.

        Args:
            page: Playwright Page object (đã login)
        """
        assert self._context is not None
        cookies = await self._context.cookies()
        cookie_file = self.config.cookies_dir / "fb_cookies.json"
        with open(cookie_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        logger.info(f"Đã lưu {len(cookies)} cookies → {cookie_file}")

    async def load_cookies(self, page: Page) -> bool:
        """Load cookies từ file đã lưu vào context.

        Args:
            page: Playwright Page object

        Returns:
            True nếu load thành công, False nếu không tìm thấy file
        """
        cookie_file = self.config.cookies_dir / "fb_cookies.json"
        if not cookie_file.exists():
            logger.warning("Không tìm thấy cookie file. Chạy: python src/main.py login")
            return False

        assert self._context is not None
        with open(cookie_file, encoding="utf-8") as f:
            cookies = json.load(f)

        await self._context.add_cookies(cookies)
        logger.info(f"Đã load {len(cookies)} cookies")
        return True

    async def is_logged_in(self, page: Page) -> bool:
        """Kiểm tra xem session hiện tại còn đăng nhập không.

        Args:
            page: Playwright Page object

        Returns:
            True nếu đang logged in
        """
        try:
            await page.goto(
                "https://www.facebook.com",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            url = page.url
            return "login" not in url and "checkpoint" not in url
        except Exception:
            return False
