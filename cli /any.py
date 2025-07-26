import os
import re
import json
import threading
import requests
import subprocess
from queue import Queue
from datetime import datetime, timedelta
from yt_dlp import YoutubeDL
from rich import print
from rich.prompt import Prompt
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn, TransferSpeedColumn
from rich.align import Align
from rich.layout import Layout
from rich.text import Text
from rich.live import Live
from rich.traceback import install
from rich.logging import RichHandler
import logging

install()
logging.basicConfig(level="NOTSET", handlers=[RichHandler(rich_tracebacks=True)], format="%(message)s")
log = logging.getLogger("rich")

CONFIG_FILE = 'config.json'
DEFAULT_CONFIG = {
    "output_path": "downloads",
    "preferred_resolution": "best",
    "audio_only": False,
    "retry_count": 3,
    "max_threads": 4,
    "dry_run": False,
    "file_logging": True,
    "subtitles_enabled": False,
    "embed_subtitles": False,
    "subtitle_lang": "en",
    "download_thumbnail": False,
    "embed_thumbnail": False,
    "scheduled_downloads": [],
    "daily_summary_enabled": True,
    "last_summary_date": None
}

console = Console()
progress = Progress(
    TextColumn("[bold blue]{task.fields[title]}", justify="right"),
    BarColumn(),
    TransferSpeedColumn(),
    TimeElapsedColumn(),
    TimeRemainingColumn(),
    expand=True
)

file_logger = None
def setup_file_logger():
    global file_logger
    if config.get("file_logging"):
        file_logger = logging.getLogger("file_logger")
        file_logger.setLevel(logging.INFO)
        if not file_logger.hasHandlers():
            fh = logging.FileHandler("download.log")
            formatter = logging.Formatter('%(asctime)s - %(message)s')
            fh.setFormatter(formatter)
            file_logger.addHandler(fh)
    else:
        file_logger = None

def log_event(message):
    console.print(message)
    if file_logger:
        file_logger.info(message)

class Config:
    def __init__(self):
        self.data = DEFAULT_CONFIG.copy()
        self.load()
    def load(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                self.data.update(json.load(f))
    def save(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.data, f, indent=4)
    def get(self, key):
        return self.data.get(key)
    def set(self, key, value):
        self.data[key] = value
        self.save()
        if key == "file_logging":
            setup_file_logger()

config = Config()
setup_file_logger()
os.makedirs(config.get("output_path"), exist_ok=True)

def sanitize_filename(name):
    return re.sub(r'[^\w\-_\. ]', '_', name)

def build_ydl_opts(url, task_id):
    opts = {
        'format': config.get("preferred_resolution"),
        'outtmpl': os.path.join(config.get("output_path"), '%(title)s.%(ext)s'),
        'noplaylist': False,
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [lambda d: hook(d, task_id)],
        'postprocessors': [],
    }
    if config.get("audio_only"):
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'].append({
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        })
        if config.get("download_thumbnail"):
            opts['writethumbnail'] = True
            if config.get("embed_thumbnail"):
                opts['postprocessors'].append({
                    'key': 'EmbedThumbnail',
                })
    if config.get("subtitles_enabled"):
        opts['writesubtitles'] = True
        opts['writeautomaticsub'] = True
        lang = config.get("subtitle_lang")
        if lang:
            opts['subtitleslangs'] = [lang]
        else:
            opts['subtitleslangs'] = ['en']
        if config.get("embed_subtitles"):
            opts['postprocessors'].append({
                'key': 'FFmpegEmbedSubtitle',
            })
    return opts

def hook(d, task_id):
    if d['status'] == 'downloading':
        progress.update(task_id, completed=d.get("downloaded_bytes", 0), total=d.get("total_bytes", 0))
    elif d['status'] == 'finished':
        progress.update(task_id, completed=d.get("total_bytes", 0))

def get_video_info(url):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info

def download_url(url, task_id):
    for attempt in range(config.get("retry_count")):
        try:
            opts = build_ydl_opts(url, task_id)
            with YoutubeDL(opts) as ydl:
                if config.get("dry_run"):
                    info = ydl.extract_info(url, download=False)
                    subtitle_info = ""
                    if config.get("subtitles_enabled"):
                        subtitles = info.get('subtitles') or {}
                        automatic_captions = info.get('automatic_captions') or {}
                        langs = set(subtitles.keys()) | set(automatic_captions.keys())
                        if langs:
                            subtitle_info = f"\n[bold yellow]Available subtitles:[/] {', '.join(langs)}"
                    thumbnail_info = ""
                    if config.get("download_thumbnail"):
                        thumbnail_info = "\n[bold magenta]Thumbnail download enabled[/]"
                    log_event(Panel(f"[bold green]Dry-run:[/] {info.get('title')}{subtitle_info}{thumbnail_info}", title="Info Preview"))
                else:
                    ydl.download([url])
                    info = ydl.extract_info(url, download=False)
                    duration = info.get("duration")
                    duration_str = str(datetime.utcfromtimestamp(duration).strftime('%H:%M:%S')) if duration else "N/A"
                    uploader = info.get("uploader", "N/A")
                    view_count = info.get("view_count", "N/A")
                    resolution = info.get("format_note") or info.get("resolution") or config.get("preferred_resolution")
                    summary = Table.grid(padding=1)
                    summary.add_column(justify="right", style="cyan", no_wrap=True)
                    summary.add_column(style="white")
                    summary.add_row("Title:", info.get("title", "N/A"))
                    summary.add_row("Duration:", duration_str)
                    summary.add_row("Uploader:", uploader)
                    summary.add_row("Views:", str(view_count))
                    summary.add_row("Resolution:", resolution)
                    if config.get("subtitles_enabled"):
                        summary.add_row("Subtitles:", f"Enabled ({config.get('subtitle_lang')})" if config.get("embed_subtitles") else "Enabled (not embedded)")
                    else:
                        summary.add_row("Subtitles:", "Disabled")
                    if config.get("audio_only") and config.get("download_thumbnail"):
                        summary.add_row("Thumbnail Download:", "Enabled")
                        summary.add_row("Embed Thumbnail:", "Yes" if config.get("embed_thumbnail") else "No")
                    console.print(Panel(summary, title="Download Summary", subtitle=url))
            return True
        except Exception as e:
            log_event(f"[red]Error downloading {url} (attempt {attempt + 1}): {e}")
    return False

def worker(queue):
    while not queue.empty():
        url = queue.get()
        title = f"{url[:60]}..." if len(url) > 60 else url
        task_id = progress.add_task("Downloading", title=title, start=False)
        progress.start_task(task_id)
        success = download_url(url, task_id)
        queue.task_done()
        status = "✔" if success else "✖"
        log_event(f"{status} Finished: {url}")

def layout_ui():
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=3)
    )
    layout["header"].update(Align.center(Text("Universal Media Downloader CLI", style="bold white on blue")))
    layout["footer"].update(Align.center(Text("Ctrl+C to exit at any time", style="dim")))
    return layout

def show_main_menu():
    layout = layout_ui()
    table = Table(title="Main Menu")
    table.add_column("Option", justify="center", style="cyan")
    table.add_column("Description", justify="left", style="white")
    table.add_row("1", "Download a single video")
    table.add_row("2", "Download a playlist")
    table.add_row("3", "Batch download from file")
    table.add_row("4", "Settings")
    table.add_row("5", "Exit")
    table.add_row("6", "Preview video metadata")
    table.add_row("7", "Toggle subtitle download")
    table.add_row("8", "View current configuration")
    table.add_row("9", "Schedule a download")
    table.add_row("10", "Show scheduled downloads")
    table.add_row("11", "Export config and scheduled downloads")
    table.add_row("12", "Import config and scheduled downloads")
    layout["body"].update(Align.center(table))
    with Live(layout, refresh_per_second=10):
        return Prompt.ask("Choose")
def export_config_data():
    export_data = {
        "config": {k: v for k, v in config.data.items() if k != "scheduled_downloads"},
        "scheduled_downloads": config.get("scheduled_downloads")
    }
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_filename = f"config_export_{timestamp}.json"
    filename = Prompt.ask(f"Enter filename to export to", default=default_filename)
    try:
        with open(filename, "w") as f:
            json.dump(export_data, f, indent=4)
        log_event(f"[green]Exported config and scheduled downloads to {filename}")
    except Exception as e:
        log_event(f"[red]Failed to export: {e}")

def import_config_data():
    filename = Prompt.ask("Enter filename to import from")
    if not os.path.exists(filename):
        log_event(f"[red]File not found: {filename}")
        return
    try:
        with open(filename, "r") as f:
            import_data = json.load(f)
        if not isinstance(import_data, dict):
            log_event("[red]Invalid import file format (not a dict)")
            return
        config_data = import_data.get("config")
        scheduled = import_data.get("scheduled_downloads")
        if not isinstance(config_data, dict) or not isinstance(scheduled, list):
            log_event("[red]Invalid import file format (missing keys or wrong types)")
            return
        for k, v in config_data.items():
            if k in config.data:
                config.set(k, v)
        config.set("scheduled_downloads", scheduled)
        log_event(f"[green]Imported config and scheduled downloads from {filename}")
    except Exception as e:
        log_event(f"[red]Failed to import: {e}")

def show_settings():
    while True:
        layout = layout_ui()
        table = Table(title="Settings")
        for key, val in config.data.items():
            table.add_row(key, str(val))
        layout["body"].update(Align.center(table))
        with Live(layout, refresh_per_second=10):
            k = Prompt.ask("Setting to change (or 'back')")
        if k == "back":
            break
        if k in config.data:
            if k in ["subtitles_enabled", "embed_subtitles", "audio_only", "dry_run", "file_logging", "download_thumbnail", "embed_thumbnail"]:
                current_val = config.data[k]
                new_val = Prompt.ask(f"Toggle {k} (current: {current_val}) [y/n]", choices=["y", "n"], default="y" if current_val else "n")
                config.set(k, new_val == "y")
            elif k == "subtitle_lang":
                v = Prompt.ask(f"New value for {k} (e.g. en, fr, de)")
                config.set(k, v)
            elif k in ["retry_count", "max_threads"]:
                v = Prompt.ask(f"New value for {k}", default=str(config.data[k]))
                try:
                    config.set(k, int(v))
                except ValueError:
                    log_event("[red]Invalid integer value")
            else:
                v = Prompt.ask(f"New value for {k}")
                config.set(k, type(config.data[k])(v))

def single_video():
    url = Prompt.ask("Enter video URL")
    queue = Queue()
    queue.put(url)
    with progress:
        threading.Thread(target=worker, args=(queue,), daemon=True).start()
        queue.join()

def playlist_video():
    url = Prompt.ask("Enter playlist URL")
    queue = Queue()
    queue.put(url)
    with progress:
        threading.Thread(target=worker, args=(queue,), daemon=True).start()
        queue.join()

def batch_file():
    file_path = Prompt.ask("Path to batch file")
    if not os.path.exists(file_path):
        log_event("[red]File not found")
        return
    with open(file_path) as f:
        urls = [line.strip() for line in f if line.strip()]
    queue = Queue()
    for url in urls:
        queue.put(url)
    with progress:
        threads = []
        for _ in range(config.get("max_threads")):
            t = threading.Thread(target=worker, args=(queue,), daemon=True)
            t.start()
            threads.append(t)
        queue.join()

def preview_video():
    url = Prompt.ask("Enter video URL to preview metadata")
    try:
        info = get_video_info(url)
        duration = info.get("duration")
        duration_str = str(datetime.utcfromtimestamp(duration).strftime('%H:%M:%S')) if duration else "N/A"
        uploader = info.get("uploader", "N/A")
        view_count = info.get("view_count", "N/A")
        resolution = info.get("format_note") or info.get("resolution") or config.get("preferred_resolution")
        subtitles = info.get('subtitles') or {}
        automatic_captions = info.get('automatic_captions') or {}
        subtitle_langs = set(subtitles.keys()) | set(automatic_captions.keys())
        subtitle_str = ", ".join(subtitle_langs) if subtitle_langs else "None"
        summary = Table.grid(padding=1)
        summary.add_column(justify="right", style="cyan", no_wrap=True)
        summary.add_column(style="white")
        summary.add_row("Title:", info.get("title", "N/A"))
        summary.add_row("Duration:", duration_str)
        summary.add_row("Uploader:", uploader)
        summary.add_row("Views:", str(view_count))
        summary.add_row("Resolution:", resolution)
        summary.add_row("Available Subtitles:", subtitle_str)
        console.print(Panel(summary, title="Video Metadata Preview", subtitle=url))
    except Exception as e:
        log_event(f"[red]Error fetching metadata: {e}")

def toggle_subtitles():
    current = config.get("subtitles_enabled")
    new_val = not current
    config.set("subtitles_enabled", new_val)
    if new_val:
        lang = Prompt.ask("Enter subtitle language code to download", default=config.get("subtitle_lang"))
        config.set("subtitle_lang", lang)
        embed = Prompt.ask("Embed subtitles into video? (y/n)", choices=["y","n"], default="n")
        config.set("embed_subtitles", embed == "y")
    else:
        config.set("embed_subtitles", False)
    status = "enabled" if new_val else "disabled"
    log_event(f"[green]Subtitle downloading {status}.")

def show_config_summary(return_text=False):
    summary = Table.grid(padding=1)
    summary.add_column(justify="right", style="cyan", no_wrap=True)
    summary.add_column(style="white")
    text_lines = []
    for key, val in config.data.items():
        summary.add_row(key, str(val))
        text_lines.append(f"{key}: {val}")
    if return_text:
        return "\n".join(text_lines)
    else:
        console.print(Panel(summary, title="Current Configuration"))
def get_scheduled_jobs_summary():
    scheduled = config.get("scheduled_downloads")
    if not scheduled:
        return "No scheduled downloads."
    lines = []
    for i, item in enumerate(scheduled, 1):
        try:
            when = datetime.fromisoformat(item["time"])
            when_str = when.strftime("%Y-%m-%d %H:%M")
        except Exception:
            when_str = "Invalid date"
        lines.append(f"{i}. URL: {item.get('url','N/A')}, Scheduled Time: {when_str}")
    return "\n".join(lines)

def write_daily_summary():
    summary_lines = []
    summary_lines.append(f"==== Daily Summary: {datetime.now().strftime('%Y-%m-%d')} ====")
    summary_lines.append("\n--- Configuration ---")
    summary_lines.append(show_config_summary(return_text=True))
    summary_lines.append("\n--- Scheduled Downloads ---")
    summary_lines.append(get_scheduled_jobs_summary())
    summary_text = "\n".join(summary_lines)
    with open("daily_summary.log", "a") as f:
        f.write(summary_text)
        f.write("\n\n")
    log_event("[green]Daily summary written to daily_summary.log")

def check_and_log_daily_summary():
    if not config.get("daily_summary_enabled"):
        return
    today_str = datetime.now().strftime("%Y-%m-%d")
    last_summary_date = config.get("last_summary_date")
    if last_summary_date != today_str:
        write_daily_summary()
        config.set("last_summary_date", today_str)

def schedule_download(url, when):
    scheduled = config.get("scheduled_downloads")
    scheduled.append({"url": url, "time": when.isoformat()})
    config.set("scheduled_downloads", scheduled)
    log_event(f"[green]Scheduled download for {url} at {when.strftime('%Y-%m-%d %H:%M:%S')}")

def check_and_process_scheduled():
    scheduled = config.get("scheduled_downloads")
    if not scheduled:
        return
    now = datetime.now()
    to_download = []
    remaining = []
    for item in scheduled:
        try:
            scheduled_time = datetime.fromisoformat(item["time"])
            if scheduled_time <= now:
                to_download.append(item["url"])
            else:
                remaining.append(item)
        except Exception:
            continue
    if to_download:
        queue = Queue()
        for url in to_download:
            queue.put(url)
        with progress:
            threads = []
            for _ in range(config.get("max_threads")):
                t = threading.Thread(target=worker, args=(queue,), daemon=True)
                t.start()
                threads.append(t)
            queue.join()
        log_event(f"[green]Processed {len(to_download)} scheduled downloads.")
    if len(remaining) != len(scheduled):
        config.set("scheduled_downloads", remaining)

def schedule_download_ui():
    url = Prompt.ask("Enter video URL to schedule")
    while True:
        when_str = Prompt.ask("Enter date and time to download (YYYY-MM-DD HH:MM, 24h format)")
        try:
            when = datetime.strptime(when_str, "%Y-%m-%d %H:%M")
            if when < datetime.now():
                log_event("[red]Scheduled time must be in the future.")
                continue
            break
        except ValueError:
            log_event("[red]Invalid datetime format. Please try again.")
    schedule_download(url, when)

def show_scheduled_downloads():
    scheduled = config.get("scheduled_downloads")
    if not scheduled:
        log_event("[yellow]No scheduled downloads.")
        return
    table = Table(title="Scheduled Downloads")
    table.add_column("Index", justify="right", style="cyan")
    table.add_column("URL", style="white")
    table.add_column("Scheduled Time", style="green")
    for i, item in enumerate(scheduled, 1):
        try:
            when = datetime.fromisoformat(item["time"])
            when_str = when.strftime("%Y-%m-%d %H:%M")
        except Exception:
            when_str = "Invalid date"
        table.add_row(str(i), item.get("url", "N/A"), when_str)
    console.print(table)

def run():
    check_and_log_daily_summary()
    while True:
        check_and_process_scheduled()
        check_and_log_daily_summary()
        choice = show_main_menu()
        if choice == "1":
            single_video()
        elif choice == "2":
            playlist_video()
        elif choice == "3":
            batch_file()
        elif choice == "4":
            show_settings()
        elif choice == "5":
            break
        elif choice == "6":
            preview_video()
        elif choice == "7":
            toggle_subtitles()
        elif choice == "8":
            show_config_summary()
        elif choice == "9":
            schedule_download_ui()
        elif choice == "10":
            show_scheduled_downloads()
        elif choice == "11":
            export_config_data()
        elif choice == "12":
            import_config_data()
        else:
            log_event("[red]Invalid choice")

if __name__ == "__main__":
    run()