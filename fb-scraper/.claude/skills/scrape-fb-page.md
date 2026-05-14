# Skill: Scrape Facebook Page (qua Web UI)

## Mô tả
Luồng đầy đủ từ khi người dùng mở browser đến khi tải được file Excel.

## Luồng người dùng

```
1. Mở http://localhost:5000
2. Nhập email + mật khẩu → click "Đăng nhập"
3. Chờ login xong (spinner) → màn hình crawl hiện ra
4. Nhập URL group + số bài + số comment → click "Bắt đầu cào"
5. Theo dõi progress bar + log stream
6. Khi xong: click "Tải file Excel"
```

## Step-by-step Implementation

### Step 1: Login flow (frontend → backend)

**Frontend (index.html):**
```javascript
async function handleLogin() {
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    if (!email || !password) { showError("Điền đầy đủ email và mật khẩu"); return; }

    setLoginLoading(true);
    const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
    });
    const data = await res.json();
    if (data.success) {
        showScreen("crawl");
    } else {
        showError(data.error || "Đăng nhập thất bại");
    }
    setLoginLoading(false);
}
```

**Backend (app.py):**
```python
@app.post("/api/login")
def api_login():
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    password = data.get("password", "")
    if not email or not password:
        return jsonify({"success": False, "error": "Email và mật khẩu không được trống"})
    
    update_state(status="logging_in")
    try:
        asyncio.run(_do_login(email, password))  # Playwright login
        update_state(status="idle")
        return jsonify({"success": True})
    except LoginError as e:
        update_state(status="idle")
        return jsonify({"success": False, "error": str(e)})
```

### Step 2: Crawl flow (frontend → backend)

**Frontend (index.html):**
```javascript
async function handleCrawl() {
    const url = document.getElementById("group-url").value.trim();
    const maxPosts = parseInt(document.getElementById("max-posts").value) || 100;
    const maxComments = parseInt(document.getElementById("max-comments").value) || 500;
    if (!url) { showError("Nhập URL group/page"); return; }

    const res = await fetch("/api/crawl", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, max_posts: maxPosts, max_comments: maxComments })
    });
    const data = await res.json();
    if (data.success) startPolling();
}
```

**Backend (app.py):**
```python
@app.post("/api/crawl")
def api_crawl():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"success": False, "error": "URL không được để trống"}), 400
    
    with _lock:
        if _state["status"] == "crawling":
            return jsonify({"success": False, "error": "Đang có crawl job chạy"}), 409
    
    max_posts = int(data.get("max_posts", 100))
    max_comments = int(data.get("max_comments", 500))
    
    update_state(status="crawling", posts=0, comments=0, logs=[], file_path=None, error=None)
    thread = threading.Thread(
        target=run_crawl_sync,
        args=(url, max_posts, max_comments),
        daemon=True
    )
    thread.start()
    return jsonify({"success": True})
```

### Step 3: Progress polling

**Backend `/api/progress`:**
```python
@app.get("/api/progress")
def api_progress():
    with _lock:
        return jsonify({
            "status": _state["status"],
            "posts": _state["posts"],
            "comments": _state["comments"],
            "logs": _state["logs"][-50:],  # Chỉ gửi 50 dòng log gần nhất
            "file_ready": _state["file_path"] is not None,
            "error": _state["error"],
        })
```

**Frontend poll mỗi 2 giây:**
```javascript
function updateUI(data) {
    document.getElementById("posts-count").textContent = data.posts;
    document.getElementById("comments-count").textContent = data.comments;
    
    const logEl = document.getElementById("log-output");
    logEl.innerHTML = data.logs.map(l => `<div>${escapeHtml(l)}</div>`).join("");
    logEl.scrollTop = logEl.scrollHeight;
    
    if (data.status === "done") {
        document.getElementById("download-btn").style.display = "block";
    }
    if (data.status === "error") {
        showError(data.error);
    }
}
```

### Step 4: Download file Excel

```python
@app.get("/api/download")
def api_download():
    with _lock:
        path = _state.get("file_path")
    if not path or not Path(path).exists():
        return jsonify({"error": "File chưa sẵn sàng"}), 404
    return send_file(path, as_attachment=True)
```

## Edge Cases

| Tình huống | Xử lý |
|-----------|-------|
| Sai mật khẩu | Trả về `{"success": false, "error": "Sai mật khẩu..."}` |
| Facebook yêu cầu OTP/2FA | Trả về error hướng dẫn tắt 2FA tạm thời |
| Đang crawl, user click crawl lần nữa | Trả về HTTP 409 "Đang có job chạy" |
| Cookie hết hạn | Kiểm tra `/api/login/status` khi load trang, redirect về login screen |
| URL group không hợp lệ | Validate trước khi chạy Playwright |
| Bị Facebook checkpoint | Cập nhật state error với message hướng dẫn |
| 0 bài tìm được | Status "done" với posts=0, Excel vẫn tạo (header only) |

## Debugging

1. Mở DevTools → Network tab → kiểm tra response từ `/api/progress`
2. Xem `logs/` để xem Playwright đang làm gì
3. Nếu selector fail: dùng researcher agent để cập nhật `SELECTORS` trong `fb_parser.py`
