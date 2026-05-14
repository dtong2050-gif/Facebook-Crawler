"""Helper functions: retry decorator, text cleaning, URL utilities."""

import asyncio
import re
import unicodedata
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Optional, TypeVar
from urllib.parse import urlparse

from utils.logger import setup_logger

logger = setup_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    max_attempts: int = 3,
    delay: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator retry cho async functions với exponential backoff.

    Args:
        max_attempts: Số lần thử tối đa
        delay: Delay ban đầu (giây), tăng gấp đôi sau mỗi lần retry
        exceptions: Tuple các exception types cần retry

    Returns:
        Decorated async function
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error: Optional[Exception] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    if attempt < max_attempts:
                        wait = delay * (2 ** (attempt - 1))
                        logger.warning(
                            f"Lần {attempt}/{max_attempts} thất bại ({type(e).__name__}): {e}. "
                            f"Thử lại sau {wait:.1f}s..."
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"Tất cả {max_attempts} lần thử đều thất bại: {e}")
            raise last_error  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator


def clean_text(text: str) -> str:
    """Làm sạch text: normalize unicode, loại bỏ control characters.

    Args:
        text: Text cần làm sạch

    Returns:
        Text đã được làm sạch, trimmed
    """
    if not text:
        return ""

    # Normalize unicode để tránh ký tự kết hợp bị duplicate
    text = unicodedata.normalize("NFC", text)

    # Loại bỏ control characters (trừ newline \n và tab \t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Normalize multiple spaces thành 1 space
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def format_timestamp(dt: Optional[datetime]) -> str:
    """Format datetime thành chuỗi YYYY-MM-DD HH:MM:SS.

    Args:
        dt: Datetime object hoặc None

    Returns:
        Chuỗi datetime hoặc "" nếu dt là None
    """
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def url_to_page_name(url: str) -> str:
    """Chuyển Facebook URL thành tên ngắn gọn cho tên file.

    Args:
        url: URL Facebook page/group

    Returns:
        Tên ngắn, chỉ chứa chữ, số và underscore

    Examples:
        "https://www.facebook.com/groups/12345" → "group_12345"
        "https://www.facebook.com/vnexpress"   → "vnexpress"
    """
    try:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = [p for p in path.split("/") if p]

        if "groups" in parts:
            idx = parts.index("groups")
            if idx + 1 < len(parts):
                return f"group_{parts[idx + 1][:40]}"

        name = parts[-1] if parts else "unknown"
    except Exception:
        name = "unknown"

    # Chỉ giữ alphanumeric và underscore
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:50] or "unknown"


def extract_post_id(url: str) -> str:
    """Trích xuất post ID từ URL Facebook.

    Args:
        url: URL bài viết Facebook

    Returns:
        Post ID string hoặc "" nếu không tìm được
    """
    if not url:
        return ""

    patterns = [
        r"/posts/(\d+)",
        r"story_fbid=(\d+)",
        r"fbid=(\d+)",
        r"/(\d{15,})",  # Chuỗi số dài thường là FB ID
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""
