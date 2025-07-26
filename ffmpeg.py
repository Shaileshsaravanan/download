import os
import platform
import subprocess
import sys

if sys.platform == "win32":
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    CREATE_NO_WINDOW = 0

def check_ffmpeg():
    try:
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            command = ["where", "ffmpeg"]
            kwargs = {
                "startupinfo": startupinfo,
                "creationflags": CREATE_NO_WINDOW
            }
        else:
            command = ["which", "ffmpeg"]
            kwargs = {}
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            **kwargs
        )
        
        if result.returncode == 0:
            ffmpeg_path = result.stdout.strip().splitlines()[0]
            if os.path.exists(ffmpeg_path) and os.access(ffmpeg_path, os.X_OK):
                return True, ffmpeg_path
                
        return False, ""

    except Exception as e:
        print(f"[FFmpeg Detection Error] {e}")
        return False, ""