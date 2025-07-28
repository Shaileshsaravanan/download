import os
import re
import json
import threading
import queue
import time
from pytube import YouTube, Playlist
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from tqdm import tqdm

console = Console()
CONFIG_FILE = "yt_downloader_config.json"
LOG_FILE = "yt_downloader_log.txt"

class Config:
    def __init__(self, path=CONFIG_FILE):
        self.path = path
        self.data = {
            "output_path": "downloads",
            "audio_only": False,
            "max_threads": 4,
            "dry_run": False
        }
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    self.data.update(json.load(f))
            except:
                pass

    def save(self):
        with open(self.path, 'w') as f:
            json.dump(self.data, f, indent=4)

    def __getitem__(self, key):
        return self.data.get(key)

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

config = Config()

def log(message):
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{time.ctime()}] {message}\n")

def sanitize_filename(name):
    return re.sub(r'[\\/:"*?<>|]+', "", name)

def get_video_info(url):
    yt = YouTube(url)
    return {
        "title": yt.title,
        "author": yt.author,
        "length": yt.length,
        "views": yt.views,
        "publish_date": str(yt.publish_date)
    }

def print_video_info(info):
    table = Table(title="Video Info")
    for k, v in info.items():
        table.add_row(k, str(v))
    console.print(table)

def download_video(url, output_path, audio_only=False, dry_run=False):
    try:
        yt = YouTube(url)
        title = sanitize_filename(yt.title)
        stream = yt.streams.filter(only_audio=True).first() if audio_only else yt.streams.get_highest_resolution()
        if dry_run:
            console.print(f"[DRY RUN] {title}")
            return True
        path = stream.download(output_path=output_path, filename=title + (".mp3" if audio_only else ".mp4"))
        log(f"Downloaded: {yt.title}")
        return True
    except Exception as e:
        log(f"Failed: {url} | Error: {e}")
        return False

def download_playlist(playlist_url, output_path, audio_only=False, dry_run=False):
    try:
        playlist = Playlist(playlist_url)
        urls = playlist.video_urls
        console.print(f"[green]Downloading Playlist: {playlist.title} with {len(urls)} videos[/green]")
        for url in urls:
            download_video(url, output_path, audio_only=audio_only, dry_run=dry_run)
    except Exception as e:
        log(f"Playlist failed: {playlist_url} | Error: {e}")

def batch_download_from_file(file_path, output_path, audio_only=False, dry_run=False, max_threads=4):
    q = queue.Queue()
    results = []

    def worker():
        while True:
            url = q.get()
            if url is None:
                break
            success = download_video(url, output_path, audio_only=audio_only, dry_run=dry_run)
            results.append((url, success))
            q.task_done()

    with open(file_path, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]

    for url in urls:
        q.put(url)

    threads = []
    for _ in range(min(max_threads, len(urls))):
        t = threading.Thread(target=worker)
        t.start()
        threads.append(t)

    q.join()

    for _ in threads:
        q.put(None)
    for t in threads:
        t.join()

    success_count = sum(1 for _, s in results if s)
    fail_count = len(results) - success_count
    console.print(f"[green]Completed batch download. Success: {success_count}, Failures: {fail_count}[/green]")

def show_menu():
    console.print("\n[bold cyan]YouTube Downloader[/bold cyan]")
    console.print("[1] Download Single Video")
    console.print("[2] Download Playlist")
    console.print("[3] Batch Download from File")
    console.print("[4] View/Update Settings")
    console.print("[5] Dry Run URL Check")
    console.print("[0] Exit")

def update_settings():
    while True:
        console.print("\n[bold yellow]Settings[/bold yellow]")
        for k, v in config.data.items():
            console.print(f"{k}: {v}")
        console.print("[a] Toggle audio_only")
        console.print("[o] Change output folder")
        console.print("[t] Set max threads")
        console.print("[d] Toggle dry run")
        console.print("[q] Back")
        choice = input("Choice: ").lower()
        if choice == 'a':
            config["audio_only"] = not config["audio_only"]
        elif choice == 'o':
            path = input("Enter new output folder: ").strip()
            config["output_path"] = path
        elif choice == 't':
            n = input("Max threads: ").strip()
            if n.isdigit():
                config["max_threads"] = int(n)
        elif choice == 'd':
            config["dry_run"] = not config["dry_run"]
        elif choice == 'q':
            break

def dry_run_check():
    url = input("Enter URL: ").strip()
    try:
        info = get_video_info(url)
        print_video_info(info)
    except Exception as e:
        console.print(f"[red]Error fetching info: {e}[/red]")

def main():
    os.makedirs(config["output_path"], exist_ok=True)
    while True:
        show_menu()
        choice = input("Select option: ").strip()
        if choice == '1':
            url = input("Enter video URL: ").strip()
            download_video(url, config["output_path"], config["audio_only"], config["dry_run"])
        elif choice == '2':
            url = input("Enter playlist URL: ").strip()
            download_playlist(url, config["output_path"], config["audio_only"], config["dry_run"])
        elif choice == '3':
            path = input("Enter path to file with URLs: ").strip()
            if os.path.exists(path):
                batch_download_from_file(path, config["output_path"], config["audio_only"], config["dry_run"], config["max_threads"])
            else:
                console.print("[red]File not found[/red]")
        elif choice == '4':
            update_settings()
        elif choice == '5':
            dry_run_check()
        elif choice == '0':
            break
        else:
            console.print("[red]Invalid choice[/red]")

if __name__ == "__main__":
    main()