"""Entry point CLI cho Facebook Scraper."""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

# Đảm bảo terminal Windows hiển thị đúng tiếng Việt và emoji
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

# Thêm src/ vào sys.path để import các module
sys.path.insert(0, str(Path(__file__).parent))

from browser.session import BrowserSession, LoginError
from config import Config
from exporters.excel_exporter import ExcelExporter
from scrapers.base import RateLimitError
from scrapers.comment_scraper import CommentScraper
from scrapers.post_scraper import PostScraper
from utils.helpers import url_to_page_name
from utils.logger import setup_logger

console = Console()
logger = setup_logger(__name__)


async def cmd_login(config: Config) -> None:
    """Đăng nhập Facebook và lưu cookie ra file.

    Args:
        config: Config object (cần fb_email và fb_password)
    """
    console.print(Panel("[bold]Đăng nhập Facebook[/bold]", style="blue", width=50))

    async with BrowserSession(config) as session:
        page = await session.new_page()
        await session.login(page, config.fb_email, config.fb_password)
        await session.save_cookies(page)

    console.print("[green]Cookie đã lưu thành công vào cookies/fb_cookies.json[/green]")


async def cmd_scrape(config: Config, max_posts: Optional[int] = None) -> None:
    """Cào dữ liệu từ tất cả target_pages trong config.

    Args:
        config: Config object
        max_posts: Override max_posts_per_page trong config
    """
    if not config.target_pages:
        console.print("[red]Lỗi: target_pages trống. Thêm URL vào config.yaml[/red]")
        return

    effective_max = max_posts or config.max_posts_per_page
    post_scraper = PostScraper(config)
    comment_scraper = CommentScraper(config)
    exporter = ExcelExporter(config.output_dir)

    total_posts = 0
    total_comments = 0

    async with BrowserSession(config) as session:
        for url in config.target_pages:
            page_name = url_to_page_name(url)
            console.print(f"\n[bold cyan]Cào:[/bold cyan] {url}")

            page = await session.new_page()
            await session.load_cookies(page)

            if not await session.is_logged_in(page):
                console.print(
                    "[red]Chưa login hoặc cookie hết hạn. "
                    "Chạy: python src/main.py login[/red]"
                )
                await page.close()
                continue

            try:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console,
                    transient=True,
                ) as progress:
                    post_task = progress.add_task(
                        f"Posts {page_name}...", total=effective_max
                    )
                    posts = await post_scraper.scrape(
                        page, url, effective_max, progress, post_task
                    )

                    if config.include_comments and posts:
                        comment_task = progress.add_task(
                            "Comments...", total=len(posts)
                        )
                        for post in posts:
                            if post.url:
                                post.comments = await comment_scraper.scrape(
                                    page, post.url, post.post_id
                                )
                            progress.advance(comment_task)

            except RateLimitError as e:
                console.print(f"[yellow]Rate limit: {e}. Bỏ qua URL này.[/yellow]")
                await page.close()
                continue

            filepath = exporter.export(posts, page_name)
            post_count = len(posts)
            comment_count = sum(len(p.comments) for p in posts)
            total_posts += post_count
            total_comments += comment_count

            console.print(f"[green]Lưu:[/green] {filepath.name}")
            console.print(f"  Posts: {post_count} | Comments: {comment_count}")

            await page.close()

    console.print(
        f"\n[bold green]Xong! "
        f"Tổng: {total_posts} posts, {total_comments} comments[/bold green]"
    )


async def cmd_test(config: Config) -> None:
    """Chạy thử với 5 bài đầu tiên.

    Args:
        config: Config object
    """
    console.print(Panel("[bold]Chạy thử — 5 bài đầu[/bold]", style="yellow", width=50))
    await cmd_scrape(config, max_posts=5)


def build_parser() -> argparse.ArgumentParser:
    """Tạo argument parser với các subcommands.

    Returns:
        Configured ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="fb-scraper",
        description="Facebook Scraper — cào bài viết và comments ra Excel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  python src/main.py login                     # Đăng nhập và lưu cookie
  python src/main.py scrape                    # Cào theo config.yaml
  python src/main.py scrape --max-posts 50     # Giới hạn 50 bài
  python src/main.py test                      # Thử nhanh với 5 bài
        """,
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    subparsers.add_parser("login", help="Đăng nhập Facebook và lưu cookie")

    scrape_parser = subparsers.add_parser("scrape", help="Cào dữ liệu từ target_pages")
    scrape_parser.add_argument(
        "--max-posts", type=int, dest="max_posts",
        help="Số bài tối đa mỗi page (override config.yaml)"
    )

    subparsers.add_parser("test", help="Chạy thử nhanh với 5 bài đầu")

    return parser


def main() -> None:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        config = Config()
    except Exception as e:
        console.print(f"[red]Lỗi load config: {e}[/red]")
        sys.exit(1)

    try:
        if args.command == "login":
            asyncio.run(cmd_login(config))
        elif args.command == "scrape":
            asyncio.run(cmd_scrape(config, getattr(args, "max_posts", None)))
        elif args.command == "test":
            asyncio.run(cmd_test(config))
    except KeyboardInterrupt:
        console.print("\n[yellow]Đã dừng bởi người dùng[/yellow]")
    except LoginError as e:
        console.print(f"[red]Lỗi login: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Lỗi không mong đợi: {e}")
        console.print(f"[red]Lỗi: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
