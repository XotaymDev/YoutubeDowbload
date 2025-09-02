from flask import Flask, render_template, request, jsonify, send_file
import requests
import yt_dlp as youtube_dl
import re
from urllib.parse import urlparse, parse_qs
import os
import tempfile

app = Flask(__name__)

# Настройки для обхода блокировок
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Папка для загрузок
DOWNLOAD_FOLDER = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# ---- ДОБАВИЛ: берём куки из переменных окружения Render ----
COOKIES_ENV = os.environ.get("YT_COOKIES")
def get_cookiefile(tmpdir):
    """Если куки заданы через ENV, сохраняем их во временный файл"""
    if not COOKIES_ENV:
        return None
    path = os.path.join(tmpdir, "cookies.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(COOKIES_ENV)
    return path
# ------------------------------------------------------------


def extract_video_id(url):
    """Извлекает ID видео из различных форматов YouTube URL"""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_video_info_via_api(video_id):
    """Получаем информацию через сторонние сервисы"""
    apis = [
        {
            'url': f'https://noembed.com/embed',
            'params': {'url': f'https://youtube.com/watch?v={video_id}'}
        },
        {
            'url': f'https://api.vevio.com/api/vevio/videos/{video_id}',
            'params': {}
        },
        {
            'url': 'https://youtube.googleapis.com/youtube/v3/videos',
            'params': {
                'part': 'snippet,contentDetails',
                'id': video_id,
                'key': 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8'
            }
        }
    ]
    
    for api in apis:
        try:
            response = requests.get(
                api['url'], 
                params=api['params'], 
                headers=HEADERS,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                
                if 'title' in data:  # noembed
                    return {
                        'title': data['title'],
                        'uploader': data.get('author_name', 'Unknown'),
                        'thumbnail': data.get('thumbnail_url'),
                        'duration': 0
                    }
                elif 'items' in data and data['items']:
                    item = data['items'][0]['snippet']
                    return {
                        'title': item['title'],
                        'uploader': item['channelTitle'],
                        'thumbnail': item['thumbnails']['high']['url'],
                        'duration': 0
                    }
                    
        except requests.RequestException:
            continue
    
    return None


def get_video_info_direct(url):
    """Прямой запрос через yt-dlp с обработкой ошибок"""
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 15,
            'source_address': '0.0.0.0',
            'force-ipv4': True,
            'http_headers': HEADERS
        }
        cookiefile = get_cookiefile(tmpdir)
        if cookiefile:
            ydl_opts['cookiefile'] = cookiefile

        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', 'Unknown Title'),
                    'uploader': info.get('uploader', 'Unknown Uploader'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail'),
                    'formats': info.get('formats', [])
                }
        except Exception as e:
            print(f"yt-dlp error: {e}")
            return None


def list_formats(url):
    """Возвращает список форматов"""
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 15,
            'source_address': '0.0.0.0',
            'force-ipv4': True,
            'http_headers': HEADERS
        }
        cookiefile = get_cookiefile(tmpdir)
        if cookiefile:
            ydl_opts['cookiefile'] = cookiefile

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            out = []
            for f in info.get('formats', []):
                out.append({
                    'format_id': f.get('format_id'),
                    'ext': f.get('ext'),
                    'vcodec': f.get('vcodec'),
                    'acodec': f.get('acodec'),
                    'fps': f.get('fps'),
                    'tbr': f.get('tbr'),
                    'height': f.get('height'),
                    'width': f.get('width'),
                    'filesize': f.get('filesize'),
                    'format_note': f.get('format_note'),
                    'url': f.get('url')
                })
            out.sort(key=lambda x: (x['height'] or 0, x['tbr'] or 0), reverse=True)
            return out


def get_direct_video_url(url, format_id=None):
    """Возвращает прямой URL для проигрывания"""
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 15,
            'source_address': '0.0.0.0',
            'force-ipv4': True,
            'http_headers': HEADERS
        }
        cookiefile = get_cookiefile(tmpdir)
        if cookiefile:
            ydl_opts['cookiefile'] = cookiefile

        if format_id:
            ydl_opts['format'] = str(format_id)
        else:
            ydl_opts['format'] = 'best[ext=mp4]/best'

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            direct = info.get('url')
            if direct:
                return {'url': direct, 'title': info.get('title'), 'uploader': info.get('uploader'), 'thumbnail': info.get('thumbnail')}
            for f in info.get('formats', []):
                if f.get('url') and (f.get('ext') == 'mp4'):
                    return {'url': f['url'], 'title': info.get('title'), 'uploader': info.get('uploader'), 'thumbnail': info.get('thumbnail')}
            for f in info.get('formats', []):
                if f.get('url'):
                    return {'url': f['url'], 'title': info.get('title'), 'uploader': info.get('uploader'), 'thumbnail': info.get('thumbnail')}
            raise RuntimeError('Direct URL not found')


# ---------------------- твои роуты ниже -----------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_video():
    url = request.form.get('url')
    format_id = request.form.get('format_id')
    if not url:
        return jsonify({'error': 'URL required'})
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
                'http_headers': HEADERS,
                'quiet': True,
                'no_warnings': True
            }
            cookiefile = get_cookiefile(tmpdir)
            if cookiefile:
                ydl_opts['cookiefile'] = cookiefile

            if format_id:
                ydl_opts['format'] = str(format_id)
            else:
                ydl_opts['format'] = 'best[ext=mp4]/best'

            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filepath = ydl.prepare_filename(info)
        
        return send_file(filepath, as_attachment=True)
    
    except Exception as e:
        return jsonify({'error': f'yt-dlp failed: {str(e)}'})


# ... остальные твои /get_info, /get_video_url, /get_formats без изменений ...
# (я добавил только cookiefile туда же, как выше)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
