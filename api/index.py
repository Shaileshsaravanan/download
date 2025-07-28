from flask import Flask, request, Response
import subprocess
import shlex
import uuid

app = Flask(__name__)

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url', '').strip()
    quality = data.get('quality', 'best')
    format_type = data.get('format', 'video')  # 'audio' or 'video'

    if not url:
        return {'error': 'No URL provided'}, 400

    filename = f"download-{uuid.uuid4()}"
    if format_type == 'audio':
        ytdlp_args = [
            'yt-dlp',
            '--extract-audio',
            '--audio-format', 'mp3',
            '--format', quality,
            '-o', '-',  # Output to stdout
            url
        ]
        content_type = 'audio/mpeg'
        download_name = filename + '.mp3'
    else:
        ytdlp_args = [
            'yt-dlp',
            '--format', quality,
            '-o', '-',  # Output to stdout
            url
        ]
        content_type = 'video/mp4'
        download_name = filename + '.mp4'

    def generate():
        process = subprocess.Popen(ytdlp_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for chunk in iter(lambda: process.stdout.read(8192), b''):
                yield chunk
        finally:
            process.terminate()

    headers = {
        'Content-Disposition': f'attachment; filename="{download_name}"',
        'Content-Type': content_type
    }

    return Response(generate(), headers=headers)

if __name__ == '__main__':
    app.run(debug=True)