# Design Rules

## Kiến trúc tổng thể

```
index.html  ──── HTTP ────►  app.py (Flask)  ──── gọi ────►  src/ (business logic)
(browser)        REST API     (state + thread)               (Playwright + scrapers)
```

Nguyên tắc: mỗi tầng chỉ biết tầng phía dưới, không import ngược.

## app.py — Flask Server

```python
# Pattern chuẩn cho endpoint login
@app.post("/api/login")
def api_login():
    data = request.get_json()
    email, password = data["email"], data["password"]
    # Chạy Playwright login sync (blocking OK)
    success, error = run_login(email, password)
    return jsonify({"success": success, "error": error})

# Pattern chuẩn cho endpoint crawl
@app.post("/api/crawl")
def api_crawl():
    data = request.get_json()
    # Validate input
    if not data.get("url"):
        return jsonify({"success": False, "error": "URL không được để trống"}), 400
    # Chạy crawl trong background thread
    thread = threading.Thread(target=run_crawl, args=(data,), daemon=True)
    thread.start()
    return jsonify({"success": True})

# Pattern chuẩn cập nhật state (luôn dùng lock)
def update_state(**kwargs):
    with _lock:
        _state.update(kwargs)
```

## index.html — Single Page App

Hai màn hình quản lý bằng CSS `display: none / block`:

```javascript
// Chuyển màn hình
function showScreen(name) {  // "login" | "crawl"
    document.getElementById("login-screen").style.display = name === "login" ? "block" : "none";
    document.getElementById("crawl-screen").style.display = name === "crawl" ? "block" : "none";
}

// Poll progress
let pollInterval = null;
function startPolling() {
    pollInterval = setInterval(async () => {
        const res = await fetch("/api/progress");
        const data = await res.json();
        updateUI(data);
        if (data.status === "done" || data.status === "error") {
            clearInterval(pollInterval);
        }
    }, 2000);
}
```

## src/ — Business Logic

- `browser/` — không biết về Flask, không biết về UI state
- `scrapers/` — dùng `browser/` và `parsers/`, không biết về `exporters/`
- `exporters/` — chỉ nhận `list[PostData]`, không biết về scraping
- `parsers/` — pure functions, không async, không side effects
- `utils/` — helpers thuần, không import từ tầng trên

## Naming Conventions

- Files: `snake_case.py`
- Classes: `PascalCase` (ví dụ: `PostScraper`, `BrowserSession`)
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE` (ví dụ: `MAX_ROWS_PER_SHEET`, `SELECTORS`)
- Private methods: `_underscore_prefix`
- Flask routes: kebab-case URL (`/api/login-status`)

## State Management (app.py)

`_state` là single source of truth cho UI:

```python
_state = {
    "status": "idle",      # idle | logging_in | crawling | done | error
    "posts": 0,            # số bài đã cào
    "comments": 0,         # số comments đã cào
    "logs": [],            # list[str], tối đa 200 phần tử
    "file_path": None,     # str path khi done
    "error": None,         # str khi error
}
```

Thêm log vào state:
```python
def add_log(msg: str) -> None:
    with _lock:
        _state["logs"].append(msg)
        if len(_state["logs"]) > 200:
            _state["logs"] = _state["logs"][-200:]
```

## Error Handling

- Login fail → `{"success": False, "error": "Sai mật khẩu hoặc bị checkpoint"}`
- Crawl error → update `_state["status"] = "error"` + `_state["error"] = msg`
- Không crash app vì lỗi của 1 request; luôn trả về JSON response hợp lệ
- Không catch bare `except:`; ít nhất là `except Exception as e:`

## Type Hints

- Tất cả function parameters và return types phải có type hint
- Dùng `dataclass` cho `PostData`, `CommentData`
- Flask route handlers: `def api_login() -> Response:` (import `Response` từ flask)
- Không dùng `Any` trừ khi không tránh được (ElementHandle của Playwright)
