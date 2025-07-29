# download

a simple web app to fetch and download videos or audio from sites like youtube, dailymotion, and more using yt-dlp.

---

## features

- paste a video url
- see available formats and quality options
- choose to download video or audio
- works directly in the browser with no extensions

---

## screenshots

![screenshot](https://hc-cdn.hel1.your-objectstorage.com/s/v3/fca7a6a4b4cdd7b5ae203385f0c93b775f5c07c5_screenshot_2025-07-29_at_8.24.44___pm.png)

---

## requirements

- python 3.8+
- flask
- yt-dlp (must be installed system-wide)
- tailwindcss (for styling, already included)

---

## setup

```bash
git clone https://github.com/shaileshsaravanan/download
cd download
pip3 install flask yt-dlp python-dotenv

python3 api/index.py
```

and open http://localhost:8000 in your browser.

---

## env variables for yt cookies

I've base64 encoded my yt cookies to allow for the yt extraction to work seamlessly. basically just export your cookies into .txt and then base64 encode it, and drop it in the .env file as the Value for the YOUTUBE_COOKIES Key and it will work.

this is to prevent errors such as the below:

![error](https://hc-cdn.hel1.your-objectstorage.com/s/v3/c5500d6d13d86dfd9f58f0430016e2f86b1cc0d3_image.png)