def normalize_url(url: str) -> str:
    if "youtube.com/shorts/" in url:
        video_id = url.split("youtube.com/shorts/")[-1].split("?")[0].split("&")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    return url


import os
import sys
import threading
import json
from typing import List, Dict, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.console import Console
from rich.progress import Progress, BarColumn, DownloadColumn, TextColumn, TimeElapsedColumn, TransferSpeedColumn, SpinnerColumn, TimeRemainingColumn
from rich.prompt import Prompt, IntPrompt
from rich.table import Table
from rich.panel import Panel
from rich import box
import ffmpeg

try:
    from pytube import YouTube, Playlist
except ImportError:
    print("Please install pytube: pip install pytube")
    sys.exit(1)

try:
    import ffmpeg
except ImportError:
    print("Please install ffmpeg-python: pip install ffmpeg-python\nAlso ensure ffmpeg is installed on your system.")
    sys.exit(1)

console = Console()
CONFIG_FILE = "yt_config.json"
DEFAULT_CONFIG = {
    "output_folder": "downloads",
    "max_threads": 4,
    "audio_format": "mp3",
    "video_format": "mp4",
    "default_quality": "highest",
    "default_bitrate": "highest",
    "dry_run": False
}

def load_config() -> Dict:
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE, "r") as f:
        cfg = json.load(f)
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = v
    return cfg

def save_config(cfg: Dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def ensure_folder_exists(path: str):
    os.makedirs(path, exist_ok=True)

def ask_url() -> str:
    return Prompt.ask("[bold cyan]Enter YouTube video or playlist URL[/]")

def ask_download_type() -> str:
    return Prompt.ask(
        "[bold magenta]Download as[/]",
        choices=["video", "audio"],
        default="video"
    )

def ask_quality_or_bitrate(type_: str, options: List[str]) -> str:
    if type_ == "video":
        prompt = "[bold green]Select video quality[/]"
    else:
        prompt = "[bold green]Select audio bitrate[/]"
    return Prompt.ask(prompt, choices=options, default=options[0])

def ask_yes_no(message: str, default: bool = True) -> bool:
    return Prompt.ask(
        f"[bold yellow]{message}[/]",
        choices=["y", "n"],
        default="y" if default else "n"
    ).lower() == "y"

def select_stream(streams, type_: str, cfg: Dict) -> Optional[object]:
    if type_ == "video":
        filtered = streams.filter(progressive=True, file_extension=cfg["video_format"])
        qualities = sorted(set(s.resolution for s in filtered), reverse=True)
        if not qualities:
            return None
        if cfg["default_quality"] == "highest":
            sel_quality = qualities[0]
        elif cfg["default_quality"] == "lowest":
            sel_quality = qualities[-1]
        else:
            sel_quality = ask_quality_or_bitrate("video", qualities)
        return filtered.filter(res=sel_quality).first()
    else:
        filtered = streams.filter(only_audio=True)
        bitrates = sorted(set(s.abr for s in filtered), reverse=True)
        if not bitrates:
            return None
        if cfg["default_bitrate"] == "highest":
            sel_bitrate = bitrates[0]
        elif cfg["default_bitrate"] == "lowest":
            sel_bitrate = bitrates[-1]
        else:
            sel_bitrate = ask_quality_or_bitrate("audio", bitrates)
        return filtered.filter(abr=sel_bitrate).first()

def convert_to_mp3(src_path: str, dest_path: str):
    try:
        ffmpeg.input(src_path).output(dest_path, format='mp3', audio_bitrate='192k').run(overwrite_output=True)
        os.remove(src_path)
    except Exception as e:
        console.print(f"[red]Failed to convert to mp3: {e}[/]")

def show_menu(cfg: Dict):
    table = Table(title="YouTube Downloader", box=box.ROUNDED)
    table.add_column("Option", style="cyan", no_wrap=True)
    table.add_column("Description", style="magenta")
    table.add_row("1", "Download single video/playlist")
    table.add_row("2", "Batch download from file")
    table.add_row("3", "Change settings")
    table.add_row("4", "Show current settings")
    table.add_row("5", "Exit")
    console.print(table)

def update_settings(cfg: Dict):
    console.print(Panel("Change Settings", style="bold magenta"))
    for k in cfg:
        if k in ["output_folder", "max_threads", "audio_format", "video_format", "default_quality", "default_bitrate", "dry_run"]:
            val = Prompt.ask(f"{k} [{cfg[k]}]", default=str(cfg[k]))
            if k == "max_threads":
                try:
                    cfg[k] = int(val)
                except ValueError:
                    console.print("[red]Invalid number, keeping previous value.[/]")
            elif k == "dry_run":
                cfg[k] = val.lower() in ("1", "true", "yes", "y")
            else:
                cfg[k] = val
    save_config(cfg)
    console.print("[green]Settings updated.[/]")

def show_settings(cfg: Dict):
    table = Table(title="Current Settings", box=box.SIMPLE)
    for k, v in cfg.items():
        table.add_row(str(k), str(v))
    console.print(table)

def get_urls_from_file(path: str) -> List[str]:
    urls = []
    with open(path, "r") as f:
        for line in f:
            url = line.strip()
            if url and not url.startswith("#"):
                urls.append(normalize_url(url))
    return urls

def download_video(
    url: str,
    cfg: Dict,
    type_: str,
    progress: Optional[Progress] = None,
    task_id: Optional[int] = None,
    dry_run: bool = False
) -> bool:
    url = normalize_url(url)
    try:
        yt = YouTube(url, on_progress_callback=None)
        title = yt.title
        streams = yt.streams
        stream = select_stream(streams, type_, cfg)
        if not stream:
            console.print(f"[red]No suitable stream found for {title} ({url})[/]")
            return False
        file_ext = cfg["audio_format"] if type_ == "audio" else cfg["video_format"]
        safe_title = "".join(c if c.isalnum() or c in " ._-" else "_" for c in title)
        output_folder = os.path.join(cfg["output_folder"], "audio" if type_ == "audio" else "video")
        ensure_folder_exists(output_folder)
        base_path = os.path.join(output_folder, safe_title)
        out_path = f"{base_path}.{file_ext}"
        if os.path.exists(out_path):
            console.print(f"[yellow]File exists, skipping: {out_path}[/]")
            return True
        if dry_run:
            console.print(f"[cyan][DRY RUN][/]: Would download: {title} ({url})")
            return True
        def on_progress(stream, chunk, bytes_remaining):
            if progress and task_id is not None:
                total = stream.filesize
                downloaded = total - bytes_remaining
                if not progress.tasks[task_id].total:
                    progress.update(task_id, total=total)
                progress.update(task_id, completed=downloaded)
        yt.register_on_progress_callback(on_progress)
        with progress or Progress() as local_progress:
            if progress is None:
                task_id = local_progress.add_task(f"Downloading [bold]{title}[/]", total=stream.filesize)
            else:
                local_progress = progress
            stream.download(output_path=output_folder, filename=f"{safe_title}.{stream.subtype}")
            if type_ == "audio" and file_ext == "mp3" and stream.subtype != "mp3":
                src_path = os.path.join(output_folder, f"{safe_title}.{stream.subtype}")
                convert_to_mp3(src_path, out_path)
        return True
    except Exception as e:
        console.print(f"[red]Failed to download {url}: {type(e).__name__} - {e}[/]")
        return False

def download_playlist(url: str, cfg: Dict, type_: str, progress: Progress, dry_run: bool = False):
    url = normalize_url(url)
    try:
        pl = Playlist(url)
        urls = pl.video_urls
        title = pl.title
        console.print(f"[bold cyan]Playlist: {title} ({len(urls)} videos)[/]")
        tasks = []
        with ThreadPoolExecutor(max_workers=cfg["max_threads"]) as executor:
            for video_url in urls:
                task_id = progress.add_task(f"[blue]Downloading", total=100)
                fut = executor.submit(download_video, video_url, cfg, type_, progress, task_id, dry_run)
                tasks.append((fut, task_id))
            for fut, task_id in tasks:
                fut.result()
                progress.remove_task(task_id)
    except Exception as e:
        console.print(f"[red]Failed to download playlist: {e}[/]")

def batch_download(urls: List[str], cfg: Dict, type_: str, dry_run: bool = False):
    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        transient=True,
    ) as progress:
        tasks = []
        with ThreadPoolExecutor(max_workers=cfg["max_threads"]) as executor:
            for url in urls:
                task_id = progress.add_task(f"[green]Batch", total=100)
                fut = executor.submit(download_video, url, cfg, type_, progress, task_id, dry_run)
                tasks.append((fut, task_id))
            for fut, task_id in tasks:
                fut.result()
                progress.remove_task(task_id)

def main():
    cfg = load_config()
    while True:
        show_menu(cfg)
        try:
            choice = IntPrompt.ask("Select option", choices=["1", "2", "3", "4", "5"], default=1)
        except Exception:
            console.print("[red]Invalid input. Try again.[/]")
            continue
        if choice == 1:
            url = normalize_url(ask_url())
            type_ = ask_download_type()
            dry_run = cfg.get("dry_run", False)
            if "playlist" in url or "list=" in url:
                with Progress(
                    SpinnerColumn(),
                    "[progress.description]{task.description}",
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeElapsedColumn(),
                    TimeRemainingColumn(),
                    transient=True,
                ) as progress:
                    download_playlist(url, cfg, type_, progress, dry_run)
            else:
                with Progress(
                    SpinnerColumn(),
                    "[progress.description]{task.description}",
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeElapsedColumn(),
                    TimeRemainingColumn(),
                    transient=True,
                ) as progress:
                    task_id = progress.add_task(f"[green]Downloading", total=100)
                    download_video(url, cfg, type_, progress, task_id, dry_run)
        elif choice == 2:
            file_path = Prompt.ask("[bold cyan]Enter path to file with URLs[/]")
            if not os.path.exists(file_path):
                console.print("[red]File not found![/]")
                continue
            urls = get_urls_from_file(file_path)
            if not urls:
                console.print("[red]No URLs found in file.[/]")
                continue
            type_ = ask_download_type()
            dry_run = cfg.get("dry_run", False)
            batch_download(urls, cfg, type_, dry_run)
        elif choice == 3:
            update_settings(cfg)
        elif choice == 4:
            show_settings(cfg)
        elif choice == 5:
            console.print("[bold green]Goodbye![/]")
            break
        else:
            console.print("[red]Invalid option.[/]")

if __name__ == "__main__":
    main()