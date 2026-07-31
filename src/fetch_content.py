"""
fetch_content.py — Step 1 & Visual Fetcher for YouTube Shorts

Inspired by MoneyPrinterTurbo:
  1. Reads sentence keywords from script.json
  2. Searches Pexels API / Pixabay / HD stock repositories for 9:16 vertical videos
  3. Downloads individual HD visual clips per sentence
  4. Also supports NASA APOD content fetching for space niche

Usage:
    python src/fetch_content.py --script output/script.json --output output/
    python src/fetch_content.py --dry-run
"""

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFont

try:
    from tenacity import (
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
        before_sleep_log,
    )
    def _make_retry():
        return retry(
            retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.Timeout)),
            stop=stop_after_attempt(4),
            wait=wait_exponential(multiplier=1, min=2, max=20),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
except ImportError:
    def _make_retry():
        def decorator(func):
            return func
        return decorator

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fetch_content")

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
NASA_APOD_URL = "https://api.nasa.gov/planetary/apod"


@_make_retry()
def fetch_pexels_video(keyword: str, pexels_api_key: str, dest_path: Path) -> Optional[Path]:
    """Search Pexels API for a 9:16 vertical video matching keyword."""
    headers = {"Authorization": pexels_api_key}
    params = {
        "query": keyword,
        "orientation": "portrait",
        "per_page": 5,
        "size": "medium",
    }
    
    logger.info(f"Searching Pexels API for vertical video: '{keyword}'...")
    resp = requests.get(PEXELS_SEARCH_URL, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    
    videos = data.get("videos", [])
    if not videos:
        logger.warning(f"No vertical videos found on Pexels for keyword '{keyword}'")
        return None

    vid = random.choice(videos[:3])
    vid_files = vid.get("video_files", [])
    
    hd_files = [vf for vf in vid_files if vf.get("width", 0) and vf.get("height", 0)]
    hd_files.sort(key=lambda x: (x.get("width", 0) * x.get("height", 0)), reverse=True)
    
    if not hd_files:
        return None
        
    video_url = hd_files[0]["link"]
    logger.info(f"Downloading Pexels video clip -> {dest_path}")
    
    with requests.get(video_url, stream=True, timeout=30) as r:
        r.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                
    return dest_path


def create_fallback_scene_image(text_label: str, keyword: str, dest_path: Path) -> Path:
    """Generate high-res procedural 9:16 visual asset when stock video API is unavailable."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1080, 1920
    
    img = Image.new("RGB", (width, height), (15, 20, 30))
    draw = ImageDraw.Draw(img)
    
    for r in range(400, 100, -50):
        draw.ellipse([width//2 - r, height//2 - r, width//2 + r, height//2 + r],
                     outline=(40, 60, 90), width=4)
        
    draw.rectangle([80, height//2 - 200, width - 80, height//2 + 200],
                   fill=(25, 35, 55), outline=(212, 175, 55), width=4)
    
    try:
        font_lg = ImageFont.truetype("arial.ttf", 52)
        font_sm = ImageFont.truetype("arial.ttf", 36)
    except IOError:
        font_lg = ImageFont.load_default()
        font_sm = ImageFont.load_default()
        
    draw.text((width//2, height//2 - 60), keyword.upper(), fill=(212, 175, 55), font=font_lg, anchor="mm")
    
    words = text_label.split()
    lines = []
    curr = ""
    for w in words:
        if len(curr + " " + w) <= 30:
            curr += " " + w
        else:
            lines.append(curr.strip())
            curr = w
    if curr:
        lines.append(curr.strip())
        
    y = height//2 + 20
    for line in lines[:3]:
        draw.text((width//2, y), line, fill=(255, 255, 255), font=font_sm, anchor="mm")
        y += 45

    img.save(dest_path, "JPEG", quality=95)
    logger.info(f"Generated procedural visual scene -> {dest_path}")
    return dest_path


def fetch_multi_scene_content(script_data: dict, output_dir: Path) -> List[dict]:
    """
    Fetch / generate scene visual clips matching every sentence in the script.
    """
    scenes_dir = output_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    
    pexels_key = os.environ.get("PEXELS_API_KEY", "").strip()
    sentences = script_data.get("sentences", [])
    
    if not sentences:
        narration = script_data.get("narration", "Luxury Real Estate Tour")
        sentences = [{"text": narration, "keywords": [script_data.get("title_keyword", "Real Estate")]}]
        
    scenes_meta = []
    
    for i, s in enumerate(sentences):
        text = s.get("text", "")
        keywords = s.get("keywords", ["luxury property"])
        kw = keywords[0] if keywords else "real estate"
        
        video_dest = scenes_dir / f"scene_{i}.mp4"
        image_dest = scenes_dir / f"scene_{i}.jpg"
        
        fetched_path = None
        media_type = "image"
        
        if pexels_key:
            try:
                fetched_path = fetch_pexels_video(kw, pexels_key, video_dest)
                if fetched_path:
                    media_type = "video"
            except Exception as e:
                logger.warning(f"Pexels fetch failed for '{kw}': {e}")

        if not fetched_path:
            fetched_path = create_fallback_scene_image(text, kw, image_dest)
            media_type = "image"

        scenes_meta.append({
            "scene_index": i,
            "text": text,
            "keyword": kw,
            "media_path": str(fetched_path),
            "media_type": media_type,
        })
        
    save_json({"scenes": scenes_meta}, output_dir / "scenes_meta.json")
    return scenes_meta


def fetch_apod(api_key: str, output_dir: Path, date: Optional[str] = None) -> dict:
    """Fetch NASA APOD for space niche."""
    params = {"api_key": api_key}
    if date:
        params["date"] = date
    resp = requests.get(NASA_APOD_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    
    img_url = data.get("hdurl") or data.get("url")
    if img_url and data.get("media_type") == "image":
        dest = output_dir / "apod_image.jpg"
        with requests.get(img_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
        data["local_image_path"] = str(dest)
    return data


def save_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


_DRY_RUN_SCENES = [
    {
        "scene_index": 0,
        "text": "Inside this $100 Million Mega Mansion lies a secret room hidden behind a waterfall.",
        "keyword": "luxury mansion pool",
        "media_path": "output/scenes/scene_0.jpg",
        "media_type": "image"
    },
    {
        "scene_index": 1,
        "text": "The primary suite spans 3,000 square feet with 24-karat gold finishes.",
        "keyword": "luxury penthouse bedroom",
        "media_path": "output/scenes/scene_1.jpg",
        "media_type": "image"
    },
    {
        "scene_index": 2,
        "text": "An underground garage houses up to twenty supercar collectibles.",
        "keyword": "luxury garage supercar",
        "media_path": "output/scenes/scene_2.jpg",
        "media_type": "image"
    },
    {
        "scene_index": 3,
        "text": "Subscribe for daily luxury real estate tours and secrets!",
        "keyword": "luxury home living room",
        "media_path": "output/scenes/scene_3.jpg",
        "media_type": "image"
    }
]


def main():
    parser = argparse.ArgumentParser(description="Fetch multi-clip visual content for Short.")
    parser.add_argument("--script", default="output/script.json", help="Path to script.json")
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Use dry-run fixture")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        scenes_dir = output_dir / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        for scene in _DRY_RUN_SCENES:
            create_fallback_scene_image(scene["text"], scene["keyword"], Path(scene["media_path"]))
        save_json({"scenes": _DRY_RUN_SCENES}, output_dir / "scenes_meta.json")
        print(json.dumps({"scenes": _DRY_RUN_SCENES}, indent=2))
        return

    script_path = Path(args.script)
    if script_path.exists():
        with open(script_path, encoding="utf-8") as f:
            script_data = json.load(f)
    else:
        from src.generate_script import get_fallback_script
        script_data = get_fallback_script("real_estate")

    scenes_meta = fetch_multi_scene_content(script_data, output_dir)
    print(json.dumps({"scenes": scenes_meta}, indent=2))


if __name__ == "__main__":
    main()
