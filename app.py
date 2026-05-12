import os
import threading
from datetime import datetime

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from crawler import FacebookCrawler

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

_lock = threading.Lock()
_crawler: FacebookCrawler | None = None

_state = {
    'status': 'idle',       # idle | logging_in | running | done | stopped | error
    'user_name': None,
    'posts': 0,
    'comments': 0,
    'logs': [],
    'error': None,
    'file_path': None,
}


def _get():
    with _lock:
        return dict(_state)


def _set(**kw):
    with _lock:
        _state.update(kw)


def _log(msg: str, t: str = 'info'):
    with _lock:
        _state['logs'].append({
            'time': datetime.now().strftime('%H:%M:%S'),
            'msg': msg,
            'type': t,
        })
        if len(_state['logs']) > 200:
            _state['logs'] = _state['logs'][-200:]


# ------------------------------------------------------------------ routes

@app.get('/')
def index():
    return send_file('index.html')


@app.post('/api/login')
def api_login():
    global _crawler
    data = request.get_json(silent=True) or {}
    email    = (data.get('email') or '').strip()
    password = (data.get('password') or '').strip()

    if not email or not password:
        return jsonify(success=False, message='Vui lòng nhập email và mật khẩu'), 400

    _set(status='logging_in', logs=[], error=None, file_path=None,
         posts=0, comments=0, user_name=None)
    _log('Đang khởi động trình duyệt Chrome...')

    if _crawler:
        _crawler.close()
    _crawler = FacebookCrawler(log_fn=_log)

    ok, msg, user = _crawler.login(email, password)
    if ok:
        _set(status='idle', user_name=user)
        _log(f'Đã đăng nhập: {user}', 'success')
        return jsonify(success=True, message=msg, user_name=user)
    else:
        _set(status='error', error=msg)
        _log(msg, 'error')
        return jsonify(success=False, message=msg), 401


@app.post('/api/logout')
def api_logout():
    global _crawler
    if _crawler:
        _crawler.close()
        _crawler = None
    _set(status='idle', user_name=None, posts=0, comments=0,
         logs=[], file_path=None, error=None)
    return jsonify(success=True)


@app.post('/api/crawl')
def api_crawl():
    global _crawler
    if not _crawler or not _crawler.is_logged_in:
        return jsonify(success=False, message='Chưa đăng nhập'), 401

    data = request.get_json(silent=True) or {}
    url          = (data.get('url') or '').strip()
    limit        = min(int(data.get('limit') or 100), 10_000)
    max_comments = min(int(data.get('max_comments') or 0), 2_000)

    if not url:
        return jsonify(success=False, message='Vui lòng nhập link group'), 400

    _set(status='running', posts=0, comments=0, logs=[], file_path=None, error=None)
    _log(f'Bắt đầu crawl: {url}')

    def _run():
        _crawler.crawl_group(url, limit, max_comments, _set, _log)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify(success=True)


@app.post('/api/stop')
def api_stop():
    if _crawler:
        _crawler.stop()
    _set(status='stopped')
    _log('Người dùng dừng crawl', 'warn')
    return jsonify(success=True)


@app.get('/api/progress')
def api_progress():
    return jsonify(_get())


@app.get('/api/download')
def api_download():
    fp = _get().get('file_path')
    if fp and os.path.exists(fp):
        return send_file(fp, as_attachment=True, download_name=os.path.basename(fp))
    return jsonify(error='File chưa sẵn sàng'), 404


# ------------------------------------------------------------------ main

if __name__ == '__main__':
    print('\n  Facebook Group Crawler')
    print('  http://localhost:5000\n')
    app.run(host='0.0.0.0', port=19876, debug=False, threaded=True)
