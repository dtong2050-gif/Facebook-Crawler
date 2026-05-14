"""Base scraper: PostData, CommentData dataclasses và BaseScraper ABC."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CommentData:
    """Dữ liệu của 1 comment."""

    post_id: str
    author: str
    content: str
    scraped_at: datetime = field(default_factory=datetime.now)


@dataclass
class PostData:
    """Dữ liệu của 1 bài viết Facebook."""

    post_id: str
    url: str
    author: str = ""
    content: str = ""
    scraped_at: datetime = field(default_factory=datetime.now)
    comments: list[CommentData] = field(default_factory=list)


class ScraperError(Exception):
    """Lỗi chung trong quá trình scraping."""


class LoginError(Exception):
    """Lỗi đăng nhập hoặc session hết hạn."""


class RateLimitError(ScraperError):
    """Facebook đang rate limit hoặc block request."""


class BaseScraper(ABC):
    """Abstract base class cho tất cả scrapers."""

    @abstractmethod
    async def scrape(self, *args: object, **kwargs: object) -> list:
        """Cào dữ liệu chính."""

    def validate(self, data: list) -> list:
        return [item for item in data if item is not None]
