import asyncio
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

# Thêm src/ vào sys.path để import các module
sys.path.insert(0, str(Path(__file__).parent / "src"))

from browser.anti_detect import natural_scroll, random_delay
from browser.session import BrowserSession, LoginError
from config import Config
from exporters.excel_exporter import ExcelExporter
from scrapers.comment_scraper import CommentScraper
from scrapers.post_scraper import PostScraper
from utils.helpers import url_to_page_name

# ──────────────────────────────────────────────────────────────────────────────
# Background async event loop — Playwright phải chạy trong asyncio context.
# Loop này chạy mãi trong 1 daemon thread; mọi coroutine Playwright đều được
# submit vào đây qua run_async() / fire_async().
# ──────────────────────────────────────────────────────────────────────────────
_bg_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
threading.Thread(target=_bg_loop.run_forever, daemon=True, name="playwright-loop").start()


def run_async(coro, timeout: float = 120):
    """Submit coroutine vào background loop, block cho đến khi có kết quả."""
    return asyncio.run_coroutine_threadsafe(coro, _bg_loop).result(timeout=timeout)


def fire_async(coro) -> None:
    """Submit coroutine vào background loop mà không chờ kết quả."""
    asyncio.run_coroutine_threadsafe(coro, _bg_loop)


# ──────────────────────────────────────────────────────────────────────────────
# Flask app
# ──────────────────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

# ──────────────────────────────────────────────────────────────────────────────
# Global state — chỉ đọc/ghi qua _get() / _set() / _log() với _lock
# ──────────────────────────────────────────────────────────────────────────────
_lock = threading.Lock()
_stop_flag = threading.Event()
_pause_flag = threading.Event()  # tạm dừng — vòng lặp crawl sẽ đứng yên cho đến khi clear

_session: BrowserSession | None = None
_page = None  # playwright Page, giữ sống suốt session

_state: dict = {
    "status": "idle",       # idle | logging_in | running | done | stopped | error
    "user_name": None,
    "posts": 0,
    "comments": 0,
    "logs": [],
    "error": None,
    "file_path": None,
}


def _get() -> dict:
    with _lock:
        return dict(_state)


def _set(**kw) -> None:
    with _lock:
        _state.update(kw)


def _log(msg: str, t: str = "info") -> None:
    with _lock:
        _state["logs"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "msg": msg,
            "type": t,
        })
        if len(_state["logs"]) > 200:
            _state["logs"] = _state["logs"][-200:]


# ──────────────────────────────────────────────────────────────────────────────
# Async Playwright operations
# ──────────────────────────────────────────────────────────────────────────────

async def _async_login(email: str, password: str) -> str:
    """Khởi động Chrome, đăng nhập FB, trả về tên người dùng."""
    global _session, _page

    # Đóng session cũ nếu có
    if _session is not None:
        try:
            await _session.__aexit__(None, None, None)
        except Exception:
            pass
        _session = None
        _page = None

    config = Config()
    _log("Đang khởi động trình duyệt Chrome...")

    _session = BrowserSession(config)
    await _session.__aenter__()
    _page = await _session.new_page()

    _log("Đang điền thông tin đăng nhập...")
    await _session.login(_page, email, password)

    # Poll URL tối đa 120s — xử lý cả trường hợp 2FA
    _log("Đang chờ đăng nhập...")
    notified_2fa = False
    for _ in range(60):  # 60 × 2s = 120s
        url = _page.url
        is_fb = "facebook.com" in url
        is_login = "/login" in url
        is_2fa = "two_step_verification" in url or "checkpoint" in url

        if is_fb and not is_login and not is_2fa:
            break  # đăng nhập thành công

        if is_2fa and not notified_2fa:
            _log(
                "⚠️ Facebook yêu cầu xác minh 2 bước — "
                "hoàn thành trong cửa sổ Chrome, app sẽ tự tiếp tục.",
                "warn",
            )
            notified_2fa = True

        await asyncio.sleep(2)
    else:
        raise LoginError(
            f"Timeout chờ đăng nhập (120s). URL hiện tại: {_page.url}"
        )

    await _session.save_cookies(_page)

    # Lấy tên người dùng từ header Facebook
    user_name = "Facebook User"
    try:
        for selector in [
            '[aria-label*="Tài khoản"] span',
            '[data-testid="blue_bar_profile_link"] span',
            'div[role="navigation"] span[dir="auto"]',
        ]:
            el = await _page.query_selector(selector)
            if el:
                text = (await el.inner_text()).strip()
                if text and len(text) < 60:
                    user_name = text
                    break
    except Exception:
        pass

    return user_name


async def _async_logout() -> None:
    """Đóng browser session."""
    global _session, _page
    if _session is not None:
        try:
            await _session.__aexit__(None, None, None)
        except Exception:
            pass
        _session = None
        _page = None


async def _await_unpause() -> None:
    """Đứng yên trong khi _pause_flag được set. Trả về khi resume hoặc stop."""
    notified = False
    while _pause_flag.is_set() and not _stop_flag.is_set():
        if not notified:
            _log("⏸ Đã tạm dừng — chờ bạn chọn 'Crawl tiếp' hoặc 'Ngừng & xuất Excel'", "warn")
            notified = True
        await asyncio.sleep(0.4)
    if notified and not _stop_flag.is_set():
        _log("▶ Tiếp tục crawl", "info")


async def _async_crawl(url: str, limit: int, max_comments: int) -> None:
    """Crawl bài viết và comments, cập nhật _state sau mỗi bước."""
    config = Config()
    post_scraper = PostScraper(config)
    comment_scraper = CommentScraper(config)
    exporter = ExcelExporter(config.output_dir)

    try:
        # ── Phase 1: Thu thập bài viết ────────────────────────────────
        _log("Đang tải trang...")
        # domcontentloaded vì FB không bao giờ đạt networkidle
        await _page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await random_delay(2, 3)  # đợi feed render sau khi DOM load

        if "checkpoint" in _page.url or ("login" in _page.url and "facebook.com" in _page.url):
            raise Exception(
                "Bị redirect về trang đăng nhập. "
                "Vui lòng đăng xuất và đăng nhập lại."
            )

        _log("[Phase 1] Bắt đầu thu thập bài viết... [v4-debug]")
        posts = []
        seen_ids: set[str] = set()
        no_new_streak = 0       # số lần scroll liên tiếp không có bài mới
        scroll_num = 0
        max_scrolls = limit * 5  # giới hạn an toàn để tránh vòng lặp vô tận

        # Move chuột vào giữa feed area — wheel events cần mouse position hợp lệ
        await _page.mouse.move(683, 400)

        while len(posts) < limit and scroll_num < max_scrolls:
            await _await_unpause()
            if _stop_flag.is_set():
                break

            batch = await post_scraper._extract_posts_from_page(_page)
            added = 0
            for post in batch:
                if post.post_id not in seen_ids:
                    seen_ids.add(post.post_id)
                    posts.append(post)
                    added += 1
                    if len(posts) >= limit:
                        break

            if added:
                _set(posts=len(posts))
                _log(f"[Phase 1] Scroll {scroll_num + 1}: +{added} bài → tổng {len(posts)}")
                no_new_streak = 0
            else:
                no_new_streak += 1
                # Báo cáo mỗi 5 lần stuck để biết đang chờ FB
                if no_new_streak % 5 == 0:
                    total_articles = await _page.evaluate(
                        "document.querySelectorAll('[role=\"article\"]').length"
                    )
                    _log(
                        f"[Phase 1] Stuck {no_new_streak}/25 — đợi FB load thêm "
                        f"(DOM hiện có {total_articles} articles)",
                        "warn",
                    )
                if no_new_streak >= 25:
                    _log("[Phase 1] Không còn bài mới, dừng scroll sớm.", "warn")
                    break

            if len(posts) >= limit:
                break

            # Chiến lược scroll theo mức độ stuck
            if no_new_streak == 0:
                # Tìm thấy bài mới — scroll tự nhiên
                await natural_scroll(_page)
                await random_delay(config.delay_min, config.delay_max)
            elif no_new_streak <= 4:
                # Stuck nhẹ — wheel event mạnh (FB cần wheel events thật)
                await _page.mouse.wheel(0, 2500)
                await asyncio.sleep(2.5)
            else:
                # Stuck nặng — kết hợp nhiều chiến lược
                await _page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.6)
                try:
                    await _page.keyboard.press("End")
                except Exception:
                    pass
                await asyncio.sleep(0.6)
                await _page.mouse.wheel(0, 3500)
                await asyncio.sleep(4.0)
            scroll_num += 1

        posts = posts[:limit]
        _set(posts=len(posts))
        _log(f"[Phase 1] Hoàn thành: {len(posts)} bài viết", "success")

        # ── Phase 2: Thu thập bình luận ───────────────────────────────
        if max_comments > 0 and posts:
            _log(f"[Phase 2] Bắt đầu lấy bình luận ({len(posts)} bài)...")
            total_comments = 0

            for i, post in enumerate(posts):
                await _await_unpause()
                if _stop_flag.is_set():
                    break
                if post.url:
                    post.comments = await comment_scraper.scrape(
                        _page, post.url, post.post_id, max_comments
                    )
                    total_comments += len(post.comments)
                    _set(comments=total_comments)
                    _log(
                        f"[Phase 2] Comment bai {i + 1}/{len(posts)}: "
                        f"{len(post.comments)} bình luận"
                    )

            _log(f"[Phase 2] Hoàn thành: {total_comments} bình luận", "success")

        # ── Phase 3: Xuất Excel ───────────────────────────────────────
        # Luôn export nếu có ít nhất 1 bài — dù người dùng bấm "Ngừng & xuất Excel"
        stopped = _stop_flag.is_set()
        if not posts:
            if stopped:
                _set(status="stopped")
                _log("Đã dừng — chưa có bài viết nào để xuất.", "warn")
            return

        _log(f"[Phase 3] Đang tạo file Excel ({'một phần' if stopped else 'đầy đủ'})...")
        file_path = exporter.export(posts, url_to_page_name(url))
        final_status = "stopped" if stopped else "done"
        _set(status=final_status, file_path=str(file_path))
        prefix = "⏹ Dừng & lưu" if stopped else "✓ Hoàn tất! Đã lưu"
        _log(f"{prefix}: {file_path.name}", "success")

    except Exception as exc:
        import traceback

        _set(status="error", error=str(exc))
        _log(f"Lỗi: {exc}", "error")
        lines = [l for l in traceback.format_exc().splitlines() if l.strip()]
        if lines:
            _log(lines[-1], "error")


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return send_file("index.html")


@app.post("/api/login")
def api_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = (data.get("password") or "").strip()

    if not email or not password:
        return jsonify(success=False, message="Vui lòng nhập email và mật khẩu"), 400

    _set(
        status="logging_in", logs=[], error=None,
        file_path=None, posts=0, comments=0, user_name=None,
    )
    _log("Đang khởi động trình duyệt Chrome...")

    try:
        user_name = run_async(_async_login(email, password), timeout=120)
        _set(status="idle", user_name=user_name)
        _log(f"Đã đăng nhập: {user_name}", "success")
        return jsonify(success=True, message="Đăng nhập thành công", user_name=user_name)
    except LoginError as e:
        _set(status="error", error=str(e))
        _log(str(e), "error")
        return jsonify(success=False, message=str(e)), 401
    except Exception as e:
        _set(status="error", error=str(e))
        _log(str(e), "error")
        return jsonify(success=False, message=str(e)), 500


@app.post("/api/logout")
def api_logout():
    fire_async(_async_logout())
    _set(
        status="idle", user_name=None, posts=0, comments=0,
        logs=[], file_path=None, error=None,
    )
    return jsonify(success=True)


@app.post("/api/crawl")
def api_crawl():
    if _session is None:
        return jsonify(success=False, message="Chưa đăng nhập"), 401

    with _lock:
        if _state["status"] == "running":
            return jsonify(success=False, message="Đang có tiến trình chạy, vui lòng chờ"), 409

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    limit = min(int(data.get("limit") or 100), 10_000)
    max_comments = min(int(data.get("max_comments") or 0), 2_000)

    if not url:
        return jsonify(success=False, message="Vui lòng nhập link group"), 400

    _stop_flag.clear()
    _pause_flag.clear()
    _set(status="running", posts=0, comments=0, logs=[], file_path=None, error=None)
    _log(f"Bắt đầu crawl: {url}")

    fire_async(_async_crawl(url, limit, max_comments))
    return jsonify(success=True)


@app.post("/api/pause")
def api_pause():
    """Tạm dừng crawl — vòng lặp đứng yên, người dùng có thể resume hoặc stop."""
    if not _pause_flag.is_set():
        _pause_flag.set()
        _set(status="paused")
    return jsonify(success=True)


@app.post("/api/resume")
def api_resume():
    """Tiếp tục crawl sau khi pause."""
    _pause_flag.clear()
    _set(status="running")
    return jsonify(success=True)


@app.post("/api/stop")
def api_stop():
    """Dừng hẳn crawl — code sẽ thoát vòng lặp và xuất Excel với data đã có."""
    _stop_flag.set()
    _pause_flag.clear()  # nếu đang pause thì release để vòng lặp tiếp tục → thoát
    _log("Người dùng dừng crawl — sẽ xuất Excel với dữ liệu đã thu được", "warn")
    return jsonify(success=True)


@app.get("/api/progress")
def api_progress():
    return jsonify(_get())


@app.get("/api/download")
def api_download():
    fp = _get().get("file_path")
    if fp and os.path.exists(fp):
        return send_file(fp, as_attachment=True, download_name=os.path.basename(fp))
    return jsonify(error="File chưa sẵn sàng"), 404


# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n  Facebook Group Crawler")
    print("  http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
