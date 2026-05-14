# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# Install dependencies
py -m pip install -r requirements.txt

# Start the Flask server (runs on port 19876)
py app.py
```

The app is then accessible at **http://localhost:19876**.

To kill stale server instances before restarting:
```powershell
Get-Process | Where-Object { $_.Name -match "py|python" } | Stop-Process -Force
```

## Architecture

This is a single-page web app for crawling Facebook Group posts and comments. It has three layers:

**[app.py](app.py)** — Flask REST API + static file server
- Serves `index.html` at `/`
- Manages a single global `FacebookCrawler` instance (`_crawler`) protected by `threading.Lock`
- Tracks shared state dict `_state` (status, posts count, comments count, logs, file path)
- Crawl runs in a background `threading.Thread`; frontend polls `/api/progress` to get updates

**[crawler.py](crawler.py)** — Selenium automation with `undetected_chromedriver`
- `FacebookCrawler.login()` — opens Chrome, fills login form, waits up to 120s for successful redirect
- `FacebookCrawler.crawl_group()` — 3-phase pipeline:
  - **Phase 1**: Scroll the group feed, extract posts via `_JS_EXTRACT_POSTS`
  - **Phase 2**: Visit each post URL, extract comments via `_JS_EXTRACT_COMMENTS`  
  - **Phase 3**: Export results to `.xlsx` via pandas + openpyxl
- JavaScript extraction is done by injecting inline JS strings (`_JS_EXTRACT_POSTS`, `_JS_DEBUG_DOM`, `_JS_EXTRACT_COMMENTS`) via `driver.execute_script()`

**[index.html](index.html)** — Self-contained SPA (no build step, no framework)
- Vanilla JS + inline CSS, dark theme
- Polls `/api/progress` every 2 seconds while crawling
- All UI state managed in JS; no external dependencies

## Key Implementation Details

**Post selector fallback chain** — Facebook's DOM changes frequently. The JS extractor tries selectors in order:
1. `[role="article"][aria-posinset]` (old layout)
2. `[role="feed"] [role="article"]` (current layout)
3. Any `[role="article"]` containing a `/posts/` or `story_fbid` link

**Port** — hardcoded to `19876` in `app.py` (`app.run(..., port=19876)`). The `start.bat` also references this port.

**Output files** — Excel files are written to the project root directory, named `fb_{group_id}_{timestamp}.xlsx`. They are gitignored via `*.xlsx`.

**`undetected_chromedriver`** — if the `uc` import fails, falls back to plain `selenium.webdriver.Chrome`. Chrome must be installed on the system.
