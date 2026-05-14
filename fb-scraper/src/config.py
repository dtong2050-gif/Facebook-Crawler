"""Load và quản lý config từ .env và config.yaml."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


@dataclass
class Config:
    """Cấu hình toàn bộ ứng dụng, load từ .env và config.yaml."""

    # Facebook credentials
    fb_email: str = ""
    fb_password: str = ""

    # Target pages
    target_pages: list[str] = field(default_factory=list)

    # Scraping config
    scroll_times: int = 10
    delay_min: float = 2.0
    delay_max: float = 5.0
    max_posts_per_page: int = 100
    include_comments: bool = True

    # Export config
    output_dir: Path = field(default_factory=lambda: Path("data"))
    filename_pattern: str = "crawl_{date}_{page_name}.xlsx"

    # Browser config
    headless: bool = False
    viewport_width: int = 1366
    viewport_height: int = 768
    cookies_dir: Path = field(default_factory=lambda: Path("cookies"))

    def __post_init__(self) -> None:
        """Load config từ .env và config.yaml sau khi khởi tạo."""
        root = Path(__file__).parent.parent

        env_file = root / ".env"
        if env_file.exists():
            load_dotenv(env_file)

        self.fb_email = os.getenv("FB_EMAIL", "")
        self.fb_password = os.getenv("FB_PASSWORD", "")

        config_file = root / "config.yaml"
        if config_file.exists():
            with open(config_file, encoding="utf-8") as f:
                raw: dict = yaml.safe_load(f) or {}
            self._apply_yaml(raw)

        # Resolve paths về absolute (tương đối với project root)
        if not self.output_dir.is_absolute():
            self.output_dir = root / self.output_dir
        if not self.cookies_dir.is_absolute():
            self.cookies_dir = root / self.cookies_dir

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_dir.mkdir(parents=True, exist_ok=True)

    def _apply_yaml(self, raw: dict) -> None:
        """Áp dụng các giá trị từ YAML vào dataclass fields.

        Args:
            raw: Dict đọc từ config.yaml
        """
        pages = raw.get("target_pages") or []
        if pages:
            self.target_pages = [str(p) for p in pages if p]

        scraping: dict = raw.get("scraping") or {}
        self.scroll_times = int(scraping.get("scroll_times", self.scroll_times))
        self.delay_min = float(scraping.get("delay_min", self.delay_min))
        self.delay_max = float(scraping.get("delay_max", self.delay_max))
        self.max_posts_per_page = int(scraping.get("max_posts_per_page", self.max_posts_per_page))
        self.include_comments = bool(scraping.get("include_comments", self.include_comments))

        export: dict = raw.get("export") or {}
        if export.get("output_dir"):
            self.output_dir = Path(export["output_dir"])
        if export.get("filename_pattern"):
            self.filename_pattern = str(export["filename_pattern"])

        browser: dict = raw.get("browser") or {}
        self.headless = bool(browser.get("headless", self.headless))
        self.viewport_width = int(browser.get("viewport_width", self.viewport_width))
        self.viewport_height = int(browser.get("viewport_height", self.viewport_height))
