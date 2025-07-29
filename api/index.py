from flask import Flask, request, render_template, Response, jsonify
from yt_dlp import YoutubeDL
import uuid
import io
from datetime import timedelta

app = Flask(__name__)

def format_views(count):
    if not count:
        return "0 views"
    for unit in ["", "k", "m", "b"]:
        if count < 1000:
            return f"{count:.0f}{unit} views"
        count /= 1000
    return f"{count:.1f}b views"

@app.route('/')
def index():
    return render_template('app.html')

@app.route('/formats', methods=['POST'])
def get_formats():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get('url') or '').strip()

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        ydl_opts = {'quiet': True, 'skip_download': True}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])

        def format_bytes(size_bytes):
            if not size_bytes or size_bytes <= 0:
                return 'unknown size'
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size_bytes < 1024:
                    return f"{size_bytes:.1f} {unit}"
                size_bytes /= 1024
            return f"{size_bytes:.1f} PB"

        simplified_formats = []
        duration_sec = info.get('duration') or 0
        for f in formats:
            bitrate = f.get('tbr') or f.get('abr') or 0
            estimated_size = bitrate * 1000 / 8 * duration_sec if bitrate and duration_sec else 0

            simplified_formats.append({
                'format_id': f.get('format_id'),
                'ext': f.get('ext'),
                'resolution': f.get('resolution') or f.get('height') or 'unknown',
                'audio_quality': f.get('audio_quality') or f.get('asr') or 'unknown',
                'note': f.get('format_note') or f.get('format') or 'unknown',
                'filesize': format_bytes(
                    f.get('filesize') or
                    f.get('filesize_approx') or
                    estimated_size
                ),
            })

        video_info = {
            'title': info.get('title'),
            'thumbnail': info.get('thumbnail'),
            'duration': str(timedelta(seconds=info.get('duration', 0))),
            'view_count': format_views(info.get('view_count')),
            'formats': simplified_formats,
        }

        return jsonify(video_info)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url', '').strip()
    format_type = data.get('format', 'video')
    quality = data.get('quality', 'best')

    if not url or not quality:
        return jsonify({'error': 'Missing URL or format selection'}), 400

    ext = 'mp3' if format_type == 'audio' else 'mp4'
    filename = f"download-{uuid.uuid4()}.{ext}"
    buffer = io.BytesIO()

    def ydl_stream():
        ydl_opts = {
            'quiet': True,
            'format': quality,
            'outtmpl': '-',
            'noplaylist': True,
            'logtostderr': False,
            'progress_hooks': [],
            'postprocessors': [],
            'buffer': buffer
        }

        if format_type == 'audio':
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]

        class StreamWrapper(io.RawIOBase):
            def writable(self): return True
            def write(self, b):
                buffer.write(b)
                yield b

        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                buffer.seek(0)
                while True:
                    chunk = buffer.read(8192)
                    if not chunk:
                        break
                    yield chunk
        except Exception as e:
            yield f"Error: {str(e)}".encode('utf-8')

    return Response(
        ydl_stream(),
        mimetype='application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
    )

if __name__ == '__main__':
    app.run(debug=True, port=8000)