from flask import Flask, render_template, request, jsonify, send_file
import requests
import yt_dlp as youtube_dl
import re
import os

app = Flask(__name__)

# Настройки для обхода блокировок
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Папка для загрузок
DOWNLOAD_FOLDER = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Куки из переменной окружения (безопасно для Render)
COOKIES = os.environ.get("YTDLP_COOKIES")  # сюда в Render добавь свою строку cookies


def build_ydl_opts(extra_opts=None):
    """Единый билдер настроек yt-dlp"""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 15,
        'source_address': '0.0.0.0',
        'force-ipv4': True,
        'http_headers': HEADERS
    }
    # Если куки заданы — добавляем
    if COOKIES:
        opts['cookiefile'] = COOKIES
    if extra_opts:
        opts.update(extra_opts)
    return opts


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
                if 'title' in data:  # noembed format
                    return {
                        'title': data['title'],
                        'uploader': data.get('author_name', 'Unknown'),
                        'thumbnail': data.get('thumbnail_url'),
                        'duration': 0
                    }
                elif 'items' in data and data['items']:  # Google API
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
    try:
        with youtube_dl.YoutubeDL(build_ydl_opts()) as ydl:
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
    with youtube_dl.YoutubeDL(build_ydl_opts()) as ydl:
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
    opts = build_ydl_opts()
    opts['format'] = str(format_id) if format_id else 'best[ext=mp4]/best'
    with youtube_dl.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        direct = info.get('url')
        if direct:
            return {'url': direct, 'title': info.get('title'),
                    'uploader': info.get('uploader'), 'thumbnail': info.get('thumbnail')}
        for f in info.get('formats', []):
            if f.get('url') and (f.get('ext') == 'mp4'):
                return {'url': f['url'], 'title': info.get('title'),
                        'uploader': info.get('uploader'), 'thumbnail': info.get('thumbnail')}
        for f in info.get('formats', []):
            if f.get('url'):
                return {'url': f['url'], 'title': info.get('title'),
                        'uploader': info.get('uploader'), 'thumbnail': info.get('thumbnail')}
        raise RuntimeError('Direct URL not found')


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
        opts = build_ydl_opts({
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s')
        })
        opts['format'] = str(format_id) if format_id else 'best[ext=mp4]/best'
        with youtube_dl.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        return jsonify({'error': f'yt-dlp failed: {str(e)}'})


@app.route('/get_info', methods=['POST'])
def get_info():
    url = request.form.get('url')
    if not url:
        return jsonify({'error': 'URL required'})
    try:
        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'error': 'Invalid YouTube URL'})
        info = None
        if not info:
            info = get_video_info_via_api(video_id)
        if not info:
            info = {
                'title': f'Video {video_id}',
                'uploader': 'Unknown Channel',
                'duration': 0,
                'thumbnail': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
                'formats': []
            }
        return jsonify({
            'success': True,
            'info': {
                'title': info.get('title'),
                'uploader': info.get('uploader'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail'),
                'video_id': video_id
            }
        })
    except Exception as e:
        return jsonify({'error': f'Unexpected error: {str(e)}'})


@app.route('/check_connection')
def check_connection():
    test_urls = [
        'https://www.youtube.com',
        'https://www.google.com',
        'https://api.noembed.com'
    ]
    results = {}
    for url in test_urls:
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            results[url] = response.status_code == 200
        except:
            results[url] = False
    return jsonify({
        'youtube_accessible': results['https://www.youtube.com'],
        'google_accessible': results['https://www.google.com'],
        'api_accessible': results['https://api.noembed.com']
    })


@app.route('/get_video_url', methods=['POST'])
def get_video_url():
    url = request.form.get('url')
    format_id = request.form.get('format_id')
    if not url:
        return jsonify({'error': 'URL required'})
    try:
        data = get_direct_video_url(url, format_id=format_id)
        return jsonify({'success': True, 'video_url': data['url'],
                        'title': data.get('title'), 'uploader': data.get('uploader'),
                        'thumbnail': data.get('thumbnail')})
    except Exception as e:
        return jsonify({'error': f'Cannot build direct url: {str(e)}'})


@app.route('/get_formats', methods=['POST'])
def get_formats():
    url = request.form.get('url')
    if not url:
        return jsonify({'error': 'URL required'})
    try:
        formats = list_formats(url)
        simplified = []
        for f in formats:
            height = f.get('height')
            vcodec = f.get('vcodec') or 'none'
            acodec = f.get('acodec') or 'none'
            label = []
            if height:
                label.append(f"{height}p")
            if f.get('fps'):
                label.append(f"{int(f['fps'])}fps")
            if f.get('tbr'):
                label.append(f"{int(f['tbr'])}kbps")
            label.append(f"v:{vcodec}")
            label.append(f"a:{acodec}")
            simplified.append({
                'format_id': f['format_id'],
                'ext': f.get('ext'),
                'label': ' | '.join(label)
            })
        return jsonify({'success': True, 'formats': simplified})
    except Exception as e:
        return jsonify({'error': f'Cannot list formats: {str(e)}'})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
