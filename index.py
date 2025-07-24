import os
import argparse
import requests
import m3u8
from tqdm import tqdm
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

class M3U8Downloader:
    def __init__(self, url, output, threads=8, temp_dir='segments'):
        self.url = url
        self.output = output
        self.temp_dir = temp_dir
        self.threads = threads
        self.playlist = None
        self.base_uri = None
        self.key = None
        self.iv = None
        os.makedirs(self.temp_dir, exist_ok=True)

    def load_playlist(self):
        print("[*] Loading playlist...")
        self.playlist = m3u8.load(self.url)

        if self.playlist.is_variant:
            print("[*] Master playlist detected:")
            for i, pl in enumerate(self.playlist.playlists):
                stream_info = pl.stream_info
                print(f"  [{i}] {stream_info.resolution} @ {stream_info.bandwidth}bps")
            choice = int(input("Choose stream quality index: "))
            chosen_uri = self.playlist.playlists[choice].uri
            self.url = urljoin(self.url, chosen_uri)
            self.playlist = m3u8.load(self.url)

        self.base_uri = self.url.rsplit("/", 1)[0] + "/"

        if self.playlist.keys and self.playlist.keys[0]:
            key_info = self.playlist.keys[0]
            key_uri = urljoin(self.base_uri, key_info.uri)
            print(f"[*] Downloading decryption key from: {key_uri}")
            self.key = requests.get(key_uri).content
            self.iv = key_info.iv
            if self.iv:
                self.iv = bytes.fromhex(self.iv.replace("0x", ""))
            else:
                self.iv = None

    def decrypt(self, data, seq):
        iv = self.iv or seq.to_bytes(16, byteorder='big')
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        return decryptor.update(data) + decryptor.finalize()

    def download_segment(self, i, segment):
        path = os.path.join(self.temp_dir, f"seg_{i:05}.ts")
        if os.path.exists(path):
            return
        seg_url = urljoin(self.base_uri, segment.uri)
        try:
            r = requests.get(seg_url, timeout=10)
            r.raise_for_status()
            data = r.content
            if self.key:
                data = self.decrypt(data, i)
            with open(path, 'wb') as f:
                f.write(data)
        except Exception as e:
            print(f"[!] Error downloading segment {i}: {e}")

    def download_all(self):
        print(f"[*] Downloading {len(self.playlist.segments)} segments with {self.threads} threads...")
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            list(tqdm(executor.map(lambda p: self.download_segment(*p), enumerate(self.playlist.segments)),
                     total=len(self.playlist.segments), desc="Downloading"))

    def merge_ts(self):
        print("[*] Merging segments into one .ts file...")
        with open(self.output, 'wb') as out_file:
            for i in range(len(self.playlist.segments)):
                segment_path = os.path.join(self.temp_dir, f"seg_{i:05}.ts")
                with open(segment_path, 'rb') as segment_file:
                    out_file.write(segment_file.read())
        print(f"[*] Merged file saved as: {self.output}")

def main():
    parser = argparse.ArgumentParser(description="M3U8 Downloader")
    parser.add_argument("url", help="M3U8 URL")
    parser.add_argument("-o", "--output", default="output.ts", help="Output file name")
    parser.add_argument("-t", "--threads", type=int, default=8, help="Number of download threads")
    args = parser.parse_args()

    downloader = M3U8Downloader(args.url, args.output, threads=args.threads)
    downloader.load_playlist()
    downloader.download_all()
    downloader.merge_ts()

if __name__ == "__main__":
    main()