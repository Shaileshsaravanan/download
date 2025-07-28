from flask import Flask, request, render_template, Response, jsonify
import subprocess
import shlex
import uuid

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/formats', methods=['POST'])
def get_formats():
    data = request.json
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        # Run yt-dlp to get available formats in JSON
        result = subprocess.run(
            ['yt-dlp', '--no-warnings', '--dump-json', url],
            capture_output=True,
            text=True,
            check=True
        )
        info = eval(result.stdout)  # Use json.loads(result.stdout) if JSON is consistent
        formats = info.get('formats', [])
        simplified = [
            {
                'format_id': f.get('format_id'),
                'ext': f.get('ext'),
                'resolution': f.get('resolution'),
                'audio_quality': f.get('audio_quality'),
                'note': f.get('format_note') or '',
            }
            for f in formats
        ]
        return jsonify({'formats': simplified})
    except subprocess.CalledProcessError as e:
        return jsonify({'error': e.stderr.strip()}), 500


@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url', '').strip()
    format_type = data.get('format', 'video')
    quality = data.get('quality', 'best')

    if not url or not quality:
        return jsonify({'error': 'Missing URL or format selection'}), 400

    filename = f"download-{uuid.uuid4()}"
    ytdlp_args = ['yt-dlp', '--no-warnings', '-f', quality, '-o', '-', url]

    # Add audio extraction flags if user wants audio only
    if format_type == 'audio':
        ytdlp_args.insert(1, '--extract-audio')
        ytdlp_args.insert(2, '--audio-format')
        ytdlp_args.insert(3, 'mp3')

    def generate():
        process = subprocess.Popen(ytdlp_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for chunk in iter(lambda: process.stdout.read(8192), b''):
                yield chunk
        finally:
            process.terminate()

    ext = 'mp3' if format_type == 'audio' else 'mp4'
    return Response(
        generate(),
        mimetype='application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}.{ext}"'
        }
    )


if __name__ == '__main__':
    app.run(debug=True)