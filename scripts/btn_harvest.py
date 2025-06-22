import requests
import time
import os

def cache_btn_pages(start=1, end=92, out_dir="btn_cache", delay=1.5):
    os.makedirs(out_dir, exist_ok=True)
    headers = {'User-Agent': 'Mozilla/5.0'}

    for i in range(start, end + 1):
        url = f"https://www.behindthename.com/names/{i}"
        out_file = os.path.join(out_dir, f"page_{i:03}.html")

        if os.path.exists(out_file):
            print(f"[SKIP] {out_file} already exists.")
            continue

        print(f"[FETCH] Downloading page {i}...")
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(resp.text)
        else:
            print(f"[ERROR] Failed to fetch page {i}: {resp.status_code}")

        time.sleep(delay)

# Run this once to cache all pages
cache_btn_pages()

