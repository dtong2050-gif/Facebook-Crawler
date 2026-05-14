import time
import os
import random
import threading
from datetime import datetime

import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

try:
    import undetected_chromedriver as uc
    _UC = True
except ImportError:
    from selenium import webdriver
    _UC = False


# ── JavaScript injected into the page for fast bulk extraction ──────────────

_JS_EXTRACT_POSTS = r"""
(function() {
  function txt(el) { return el ? (el.textContent || '').trim() : ''; }

  const results = [];
  const seen    = new Set();

  // Thử selector theo thứ tự ưu tiên:
  // 1. aria-posinset (layout cũ)
  // 2. bài trong [role=feed] (layout mới)
  // 3. tất cả article có link bài viết
  let articles = Array.from(document.querySelectorAll('[role="article"][aria-posinset]'));
  if (articles.length === 0) {
    articles = Array.from(document.querySelectorAll('[role="feed"] [role="article"]'));
  }
  if (articles.length === 0) {
    articles = Array.from(document.querySelectorAll('[role="article"]')).filter(a =>
      a.querySelector('a[href*="/posts/"], a[href*="story_fbid"], a[href*="permalink/"]')
    );
  }

  for (const a of articles) {
    try {
      // ── Post URL ──
      const postLink = a.querySelector(
        'a[href*="/posts/"], a[href*="story_fbid"]'
      );
      const postUrl = postLink ? postLink.href : '';
      if (!postUrl) continue;
      if (seen.has(postUrl)) continue;
      seen.add(postUrl);

      // ── Author ──
      // data-ad-rendering-role="profile_name" chứa h2 > a > b
      const nameEl = a.querySelector(
        '[data-ad-rendering-role="profile_name"] h2 a b, ' +
        '[data-ad-rendering-role="profile_name"] h2 a span'
      );
      const author = nameEl ? txt(nameEl) : '';
      const authorLinkEl = a.querySelector(
        '[data-ad-rendering-role="profile_name"] h2 a'
      );
      const authorUrl = authorLinkEl ? authorLinkEl.href : '';

      // ── Content ──
      const storyEl = a.querySelector(
        '[data-ad-rendering-role="story_message"]'
      );
      let content = storyEl ? txt(storyEl) : '';
      // Fallback: longest [dir=auto]
      if (!content) {
        for (const el of a.querySelectorAll('[dir="auto"]')) {
          const t = txt(el);
          if (t.length > content.length) content = t;
        }
      }

      // ── Timestamp ── (link có aria-label như "3 ngày", "5 giờ")
      let postTime = '';
      for (const el of a.querySelectorAll('a[aria-label]')) {
        const lbl = el.getAttribute('aria-label') || '';
        if (/\d/.test(lbl) && lbl.length < 40) { postTime = lbl; break; }
      }

      // ── Reactions ── (button "Thích: 135 người" hoặc số cạnh nút Like)
      let reactions = 0;
      for (const el of a.querySelectorAll('[aria-label]')) {
        const lbl = el.getAttribute('aria-label') || '';
        if (/Thích:.*người|reaction/i.test(lbl)) {
          const n = lbl.replace(/\D/g, '');
          if (n) { reactions = parseInt(n); break; }
        }
      }
      if (!reactions) {
        // Fallback: span[dir=auto] bên trong nút Thích
        const likeBtn = a.querySelector('[aria-label="Thích"][role="button"]');
        if (likeBtn) {
          const sp = likeBtn.querySelector('span[dir="auto"]');
          if (sp) { const n = txt(sp).replace(/\D/g,''); if(n) reactions = parseInt(n); }
        }
      }

      // ── Comment count ──
      let commentCount = 0;
      const commentBtn = a.querySelector('[aria-label="Viết bình luận"][role="button"]');
      if (commentBtn) {
        const sp = commentBtn.querySelector('span[dir="auto"]');
        if (sp) { const n = txt(sp).replace(/\D/g,''); if(n) commentCount = parseInt(n); }
      }

      // ── Shares ──
      let shares = 0;
      const shareRole = a.querySelector('[data-ad-rendering-role="share_button"]');
      if (shareRole) {
        const btn = shareRole.closest('[role="button"]');
        if (btn) {
          const sp = btn.querySelector('span[dir="auto"]');
          if (sp) { const n = txt(sp).replace(/\D/g,''); if(n) shares = parseInt(n); }
        }
      }

      results.push({ aid: postUrl, author, authorUrl, content, postTime,
                     postUrl, reactions, commentCount, shares });
    } catch(e) {}
  }
  return results;
})();
"""

_JS_DEBUG_DOM = r"""
(function() {
  function txt(el) { return el ? (el.textContent||'').trim().slice(0,60) : ''; }
  const all     = Array.from(document.querySelectorAll('[role="article"]'));
  const posts   = Array.from(document.querySelectorAll('[role="article"][aria-posinset]'));
  const feed    = Array.from(document.querySelectorAll('[role="feed"] [role="article"]'));
  const withLink= all.filter(a => a.querySelector('a[href*="/posts/"],a[href*="story_fbid"],a[href*="permalink/"]'));
  const sample  = posts[0] || feed[0] || withLink[0] || all[0] || null;
  return {
    totalArticles: all.length,
    postsWithPosinset: posts.length,
    feedArticles: feed.length,
    articlesWithLink: withLink.length,
    sampleTcLen: sample ? (sample.textContent||'').length : 0,
    samplePostLink: sample ? !!(sample.querySelector('a[href*="/posts/"],a[href*="story_fbid"]')) : false,
    sampleProfileName: sample ? txt(sample.querySelector('[data-ad-rendering-role="profile_name"]')) : '',
    sampleStoryMsg: sample ? txt(sample.querySelector('[data-ad-rendering-role="story_message"]')) : '',
    sampleFirstLink: sample ? ((sample.querySelector('a[href]')||{href:''}).href||'').slice(0,80) : ''
  };
})();
"""

_JS_EXTRACT_COMMENTS = r"""
(function() {
  function tc(el) { return el ? (el.textContent||'').trim() : ''; }
  const comments = [];
  const seen = new Set();
  const articles = document.querySelectorAll('[role="article"]');

  // First article on post page is the post itself — skip it.
  for (let i = 1; i < articles.length; i++) {
    const a = articles[i];
    try {
      // Author link
      let author = '', authorUrl = '';
      for (const link of a.querySelectorAll('a[role="link"],a[href]')) {
        const t = tc(link);
        if (t && t.length < 80 && (link.href||'').includes('facebook.com')) {
          author = t; authorUrl = link.href; break;
        }
      }

      // Content (longest dir=auto)
      let content = '';
      for (const d of a.querySelectorAll('[dir="auto"]')) {
        const t = tc(d);
        if (t.length > content.length) content = t;
      }
      if (!content) content = tc(a).slice(0, 500);

      if (!author && !content) continue;
      const key = author + '|' + content.slice(0, 60);
      if (seen.has(key)) continue;
      seen.add(key);

      // Timestamp
      const abbr = a.querySelector('abbr');
      const ts = abbr ? (abbr.title || abbr.innerText.trim()) : '';

      // Likes on comment
      let likes = 0;
      for (const s of a.querySelectorAll('span[aria-label]')) {
        const lbl = s.getAttribute('aria-label') || '';
        if (/reaction|lượt thích/i.test(lbl)) {
          const n = lbl.replace(/\D/g, '');
          if (n) { likes = parseInt(n); break; }
        }
      }

      comments.push({ author, authorUrl, content, timestamp: ts, likes });
    } catch(e) {}
  }
  return comments;
})();
"""


class FacebookCrawler:
    def __init__(self, log_fn=None):
        self.driver      = None
        self.is_logged_in = False
        self._stop       = threading.Event()
        self._log        = log_fn or (lambda msg, t='info': None)

    # ── driver ──────────────────────────────────────────────────────────────

    def _init_driver(self):
        if _UC:
            opts = uc.ChromeOptions()
        else:
            from selenium.webdriver.chrome.options import Options
            opts = Options()

        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--disable-notifications')
        opts.add_argument('--lang=vi-VN,vi;q=0.9')
        opts.add_argument('--window-size=1366,900')

        self.driver = uc.Chrome(options=opts) if _UC else webdriver.Chrome(options=opts)
        self.driver.implicitly_wait(4)

    def _wait(self, selector, timeout=12, by=By.CSS_SELECTOR):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )

    def _click_if_exists(self, selector, by=By.CSS_SELECTOR):
        try:
            self.driver.find_element(by, selector).click()
            return True
        except Exception:
            return False

    def _js(self, script):
        try:
            return self.driver.execute_script(script)
        except Exception:
            return []

    # ── login ────────────────────────────────────────────────────────────────

    _LOGIN_FAIL = ('login', 'checkpoint', 'two_step', 'password',
                   'recover', 'identify', 'login/device')

    def _url_of(self, handle):
        try:
            self.driver.switch_to.window(handle)
            return self.driver.current_url
        except Exception:
            return ''

    def _is_logged_in_url(self, url):
        return 'facebook.com' in url and not any(k in url for k in self._LOGIN_FAIL)

    def login(self, email, password):
        try:
            if not self.driver:
                self._init_driver()

            self._log('Dang mo trang dang nhap Facebook...')
            self.driver.get('https://www.facebook.com/login')
            time.sleep(2)

            for sel in [
                '[data-cookiebanner="accept_button"]',
                'button[title="Chap nhan tat ca"]',
                '[data-testid="cookie-policy-manage-dialog-accept-button"]',
            ]:
                self._click_if_exists(sel)
            time.sleep(0.5)

            try:
                self._log('Dang nhap thong tin dang nhap...')
                email_field = self._wait('#email', timeout=6)
                email_field.clear()
                for ch in email:
                    email_field.send_keys(ch)
                    time.sleep(random.uniform(0.03, 0.07))

                time.sleep(random.uniform(0.3, 0.6))

                pass_field = self.driver.find_element(By.ID, 'pass')
                pass_field.clear()
                for ch in password:
                    pass_field.send_keys(ch)
                    time.sleep(random.uniform(0.03, 0.07))

                time.sleep(random.uniform(0.4, 0.7))
                self._log('Dang gui yeu cau dang nhap...')
                self.driver.find_element(By.NAME, 'login').click()
            except Exception:
                self._log('Khong tu dien duoc form — vui long dang nhap thu cong tren trinh duyet.', 'warn')

            self._log('Dang cho dang nhap... (toi da 120 giay)')
            checkpoint_logged = False

            for _ in range(120):
                time.sleep(1)
                try:
                    handles = self.driver.window_handles
                except Exception:
                    continue

                for handle in handles:
                    url = self._url_of(handle)
                    if not url:
                        continue
                    if self._is_logged_in_url(url):
                        user_name = self._get_user_name()
                        self.is_logged_in = True
                        return True, 'Dang nhap thanh cong', user_name
                    if any(k in url for k in ('checkpoint', 'two_step', 'login/device', 'login/identify')):
                        if not checkpoint_logged:
                            self._log('Can xac minh danh tinh... Hoan thanh tren trinh duyet.', 'warn')
                            checkpoint_logged = True

            return False, 'Het thoi gian cho dang nhap (120 giay)', None

        except Exception as e:
            msg = str(e).split('\n')[0].strip() or 'Loi khong xac dinh'
            return False, f'Loi: {msg}', None

    def _get_user_name(self):
        selectors = [
            # Link profile trong header
            'div[role="banner"] a[aria-label] span',
            # Avatar với tên
            '[data-pagelet="LeftRail"] a[href*="profile"] span',
            # Nav bar top
            'div[role="navigation"] a[href*="facebook.com"] span[dir="auto"]',
            # Fallback từ JS
        ]
        for sel in selectors:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    txt = el.text.strip()
                    if txt and 3 < len(txt) < 60:
                        return txt
            except Exception:
                pass
        # Thử JS để tìm tên
        try:
            name = self.driver.execute_script(r"""
                const navLinks = document.querySelectorAll('div[role="banner"] a[href]');
                for (const a of navLinks) {
                    const span = a.querySelector('span');
                    if (span) {
                        const t = span.textContent.trim();
                        if (t && t.length > 3 && t.length < 60) return t;
                    }
                }
                // Tìm trong left sidebar
                const profile = document.querySelector('[data-pagelet="ProfileActions"] span, [href*="/me/"] span');
                if (profile) return profile.textContent.trim();
                return null;
            """)
            if name and len(name) > 3:
                return name
        except Exception:
            pass
        return 'Nguoi dung Facebook'

    # ── stop ────────────────────────────────────────────────────────────────

    def stop(self):
        self._stop.set()

    # ── Phase 1 : collect posts ──────────────────────────────────────────────

    def crawl_group(self, group_url, post_limit, max_comments, set_progress, add_log):
        self._stop.clear()

        # ---- Phase 1: scroll feed and collect posts ----
        add_log(f'[Phase 1] Dieu huong den group...')
        self.driver.get(group_url)
        time.sleep(3)

        src = self.driver.page_source.lower()
        if 'nhom rieng tu' in src or 'private group' in src:
            set_progress(status='error', error='Group rieng tu, khong the crawl')
            add_log('Group nay la rieng tu', 'error')
            return

        add_log('Dang cho feed tai...')
        try:
            self._wait('[role="feed"]', timeout=15)
            add_log('Feed da tai xong', 'success')
        except TimeoutException:
            add_log('Khong tim thay feed, thu tiep tuc...', 'warn')

        # Scroll chậm từ đầu trang để trigger React lazy render từng element
        add_log('Kich hoat render noi dung...')
        self.driver.execute_script('window.scrollTo(0, 0)')
        time.sleep(1)
        for step in range(8):
            self.driver.execute_script(f'window.scrollTo(0, {(step+1)*350})')
            time.sleep(0.8)
        time.sleep(2)
        self.driver.execute_script('window.scrollTo(0, 0)')
        time.sleep(1)

        posts_map = {}   # aid -> post dict
        no_new    = 0
        scroll_n  = 0

        while len(posts_map) < post_limit and not self._stop.is_set():
            raw = self._js(_JS_EXTRACT_POSTS)
            raw = raw or []

            # Debug lần đầu
            if scroll_n == 0:
                add_log(f'[debug] JS tim duoc {len(raw)} posts')
                if not raw:
                    d = self._js(_JS_DEBUG_DOM) or {}
                    add_log(
                        f'[debug] total={d.get("totalArticles")} '
                        f'posinset={d.get("postsWithPosinset")} '
                        f'feed={d.get("feedArticles")} '
                        f'withLink={d.get("articlesWithLink")} '
                        f'postLink={d.get("samplePostLink")} '
                        f'profile="{str(d.get("sampleProfileName",""))[:30]}"',
                        'warn'
                    )

            new_this = 0
            for p in raw:
                if self._stop.is_set() or len(posts_map) >= post_limit:
                    break
                aid = p.get('aid', '')
                if not aid or aid in posts_map:
                    continue
                p['crawled_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                posts_map[aid] = p
                new_this += 1
                total_cmt = sum(x.get('commentCount', 0) for x in posts_map.values())
                set_progress(posts=len(posts_map), comments=total_cmt)
                preview = p.get('content', '')[:55].rstrip()
                add_log(
                    f'Bai #{len(posts_map)}: "{preview}..." '
                    f'— {p.get("commentCount", 0)} binh luan'
                )

            scroll_n += 1
            if new_this == 0:
                no_new += 1
                if no_new == 3:
                    # Thêm debug: đếm tổng article thô trên trang
                    total_raw = self.driver.execute_script(
                        "return document.querySelectorAll('[role=\"article\"]').length"
                    )
                    add_log(f'[debug] Tong [role=article] tren trang: {total_raw}', 'warn')
                if no_new >= 10:
                    add_log('Khong con bai viet moi de tai', 'warn')
                    break
            else:
                no_new = 0

            self.driver.execute_script('window.scrollBy(0, 900)')
            time.sleep(random.uniform(2.5, 3.5))

        posts_list = list(posts_map.values())
        add_log(
            f'[Phase 1] Hoan tat — thu thap {len(posts_list)} bai viet',
            'success'
        )

        # ---- Phase 2: crawl comment content ----
        if max_comments > 0 and not self._stop.is_set():
            add_log(f'[Phase 2] Bat dau crawl noi dung comment (toi da {max_comments}/bai)...')
            for idx, post in enumerate(posts_list):
                if self._stop.is_set():
                    break
                url = post.get('postUrl', '')
                if not url:
                    post['comments'] = []
                    continue
                add_log(f'  Comment bai #{idx+1}/{len(posts_list)}...')
                cmt_list = self._crawl_comments(url, max_comments)
                post['comments'] = cmt_list
                add_log(f'  -> {len(cmt_list)} comment', 'success')
                set_progress(
                    posts=len(posts_list),
                    comments=sum(len(p.get('comments', [])) for p in posts_list)
                )
        else:
            for post in posts_list:
                post['comments'] = []

        # ---- Phase 3: export ----
        status = 'stopped' if self._stop.is_set() else 'done'
        if posts_list:
            add_log('Dang xuat file Excel...')
            fp = self._export_excel(posts_list, group_url, max_comments > 0)
            set_progress(file_path=fp, status=status)
            add_log(f'Da luu: {os.path.basename(fp)}', 'success')
        else:
            set_progress(status='error', error='Khong thu thap duoc bai viet nao')
            add_log('Khong thu thap duoc bai viet nao', 'error')

    # ── Phase 2 helpers : comment crawling ──────────────────────────────────

    def _crawl_comments(self, post_url, max_comments):
        try:
            self.driver.get(post_url)
            time.sleep(2.5)

            # Click "Sort" dropdown if present and choose "All comments"
            # (skip if not found — not critical)
            for _ in range(15):          # attempt to load more comments
                current = self._js(_JS_EXTRACT_COMMENTS) or []
                if len(current) >= max_comments:
                    break
                if not self._click_load_more_comments():
                    break
                time.sleep(1.5)

            all_cmts = self._js(_JS_EXTRACT_COMMENTS) or []
            return all_cmts[:max_comments]
        except Exception:
            return []

    def _click_load_more_comments(self):
        """Click 'See more comments' / 'Xem them binh luan' button."""
        selectors = [
            '//div[@role="button" and (contains(.,"Xem thêm bình luận") '
            'or contains(.,"See more comments") or contains(.,"View more comments"))]',
        ]
        for xpath in selectors:
            try:
                btn = self.driver.find_element(By.XPATH, xpath)
                self.driver.execute_script('arguments[0].click()', btn)
                return True
            except Exception:
                pass
        # Fallback: scroll to bottom on post page to trigger lazy load
        prev_height = self.driver.execute_script('return document.body.scrollHeight')
        self.driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(1)
        new_height = self.driver.execute_script('return document.body.scrollHeight')
        return new_height > prev_height

    # ── Excel export ─────────────────────────────────────────────────────────

    def _export_excel(self, posts, group_url, has_comments):
        group_name = group_url.rstrip('/').split('/')[-1]
        ts         = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path  = os.path.abspath(f'fb_{group_name}_{ts}.xlsx')

        # ---- Sheet 1 : posts ----
        post_rows = []
        for i, p in enumerate(posts, 1):
            post_rows.append({
                'STT':             i,
                'Tac gia':         p.get('author', ''),
                'Link tac gia':    p.get('authorUrl', ''),
                'Noi dung':        p.get('content', ''),
                'Thoi gian dang':  p.get('postTime', ''),
                'Link bai viet':   p.get('postUrl', ''),
                'Reactions':       p.get('reactions', 0),
                'So binh luan':    p.get('commentCount', 0),
                'Luot chia se':    p.get('shares', 0),
                'Crawled luc':     p.get('crawled_at', ''),
            })
        df_posts = pd.DataFrame(post_rows)

        # ---- Sheet 2 : comments ----
        cmt_rows = []
        for i, p in enumerate(posts, 1):
            for c in p.get('comments', []):
                cmt_rows.append({
                    'Bai viet #':      i,
                    'Tac gia bai':     p.get('author', ''),
                    'Tac gia comment': c.get('author', ''),
                    'Link tac gia':    c.get('authorUrl', ''),
                    'Noi dung comment':c.get('content', ''),
                    'Thoi gian':       c.get('timestamp', ''),
                    'Likes':           c.get('likes', 0),
                })
        df_cmts = pd.DataFrame(cmt_rows)

        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df_posts.to_excel(writer, sheet_name='Bai viet', index=False)
            self._style_sheet(writer, 'Bai viet', {
                'STT': 5, 'Tac gia': 22, 'Link tac gia': 45,
                'Noi dung': 65, 'Thoi gian dang': 20,
                'Link bai viet': 55, 'Reactions': 11,
                'So binh luan': 13, 'Luot chia se': 13, 'Crawled luc': 20,
            }, wrap_col='Noi dung')

            if has_comments and not df_cmts.empty:
                df_cmts.to_excel(writer, sheet_name='Binh luan', index=False)
                self._style_sheet(writer, 'Binh luan', {
                    'Bai viet #': 9, 'Tac gia bai': 20, 'Tac gia comment': 22,
                    'Link tac gia': 45, 'Noi dung comment': 65,
                    'Thoi gian': 18, 'Likes': 8,
                }, wrap_col='Noi dung comment')

        return file_path

    @staticmethod
    def _style_sheet(writer, sheet_name, widths, wrap_col=None):
        ws = writer.sheets[sheet_name]
        hdr_fill = PatternFill('solid', fgColor='1877F2')
        hdr_font = Font(color='FFFFFF', bold=True, size=10)

        wrap_idx = None
        for i, cell in enumerate(ws[1], 1):
            cell.fill = hdr_fill
            cell.font = hdr_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            ws.column_dimensions[get_column_letter(i)].width = widths.get(cell.value, 14)
            if cell.value == wrap_col:
                wrap_idx = i

        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(
                    vertical='top',
                    wrap_text=(wrap_idx is not None and cell.column == wrap_idx)
                )

    # ── close ────────────────────────────────────────────────────────────────

    def close(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        self.driver = None
        self.is_logged_in = False
