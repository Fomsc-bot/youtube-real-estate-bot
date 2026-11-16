"""
fetch_content.py — Step 1 & Visual Fetcher for YouTube Shorts

Fetches real, relevant high-resolution photos and video clips for YouTube Shorts:
  1. Identifies BTS member or topic per sentence (Jungkook, Jin, RM, Suga, J-Hope, Jimin, V, or BTS group)
  2. Creates original BTS editorial cards from the generated script
  3. Formats each photo into 1080x1920 (9:16 vertical Short) with cinematic blurred background + sharp foreground
  4. Also supports Pexels stock video API if key is present
  5. Smooth fallback if network is offline

Usage:
    python src/fetch_content.py --script output/script.json --output output/
    python src/fetch_content.py --dry-run
"""

import argparse
from io import BytesIO
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional, List
from urllib.parse import quote, urljoin
from html.parser import HTMLParser

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

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
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
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

BTS_PAGE_MAPPINGS = {
    "jungkook": ["Jungkook", "Golden_(Jungkook_album)"],
    "jin": ["Jin_(singer)", "The_Astronaut_(song)"],
    "rm": ["RM_(musician)", "Indigo_(RM_album)"],
    "suga": ["Suga_(rapper)", "D-Day_(album)"],
    "j-hope": ["J-Hope", "Jack_in_the_Box_(album)"],
    "jimin": ["Jimin", "Face_(Jimin_album)", "Muse_(Jimin_album)"],
    "v": ["V_(singer)", "Layover_(album)"],
    "group": ["BTS", "Map_of_the_Soul:_7", "Proof_(BTS_album)", "Butter_(song)", "Dynamite_(BTS_song)"],
}

HTTP_HEADERS = {
    "User-Agent": "BTSYouTubeBot/2.0 (contact: support@youtube-automation.local; https://github.com/Fomsc-bot/youtube-real-estate-bot)"
}


def fetch_pexels_video(query: str, api_key: str, dest_path: Path) -> Optional[Path]:
    """Fetch 9:16 portrait stock video from Pexels API."""
    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "orientation": "portrait",
        "per_page": 5,
        "size": "medium",
    }
    resp = requests.get(PEXELS_SEARCH_URL, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    videos = data.get("videos", [])
    if not videos:
        return None

    chosen_video = videos[0]
    video_files = chosen_video.get("video_files", [])

    hd_vertical = next(
        (f for f in video_files if f.get("height", 0) > f.get("width", 0) and f.get("quality") == "hd"),
        None
    )
    if not hd_vertical:
        hd_vertical = next(
            (f for f in video_files if f.get("height", 0) > f.get("width", 0)),
            video_files[0] if video_files else None
        )

    if not hd_vertical or not hd_vertical.get("link"):
        return None

    video_url = hd_vertical["link"]
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(video_url, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)

    return dest_path


def _get_bts_target_pages(keyword: str, text: str) -> List[str]:
    """Determine best Wikipedia pages for the specific BTS topic/member."""
    combined = (keyword + " " + text).lower()
    if "jungkook" in combined or "jk" in combined or "golden" in combined:
        return BTS_PAGE_MAPPINGS["jungkook"]
    elif "jin" in combined or "seokjin" in combined:
        return BTS_PAGE_MAPPINGS["jin"]
    elif "suga" in combined or "yoongi" in combined or "agust" in combined:
        return BTS_PAGE_MAPPINGS["suga"]
    elif "j-hope" in combined or "jhope" in combined or "hoseok" in combined:
        return BTS_PAGE_MAPPINGS["j-hope"]
    elif "jimin" in combined:
        return BTS_PAGE_MAPPINGS["jimin"]
    elif "taehyung" in combined or " v " in combined or combined.startswith("v "):
        return BTS_PAGE_MAPPINGS["v"]
    elif "rm" in combined or "namjoon" in combined:
        return BTS_PAGE_MAPPINGS["rm"]
    return BTS_PAGE_MAPPINGS["group"]


def fetch_relevant_bts_image(keyword: str, text: str, dest_path: Path, scene_index: int = 0) -> Optional[Path]:
    """
    Fetch a real, high-resolution official photo of BTS or specific member
    from Wikipedia / Wikimedia REST API (100% Free, Public Domain / CC).
    Formats into 1080x1920 (9:16 Shorts) with blurred background + sharp foreground photo.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    target_pages = _get_bts_target_pages(keyword, text)
    img_bytes = None

    for page in target_pages:
        try:
            # 1. Try media-list endpoint to extract real high-res images from the article
            media_url = f"https://en.wikipedia.org/api/rest_v1/page/media-list/{quote(page)}"
            r = requests.get(media_url, headers=HTTP_HEADERS, timeout=8)
            if r.status_code == 200:
                items = r.json().get("items", [])
                image_urls = []
                for item in items:
                    if item.get("type") == "image":
                        title = item.get("title", "").lower()
                        # Skip logos, signatures, and icons
                        if any(ext in title for ext in ["signature", "logo", "icon", "star", "symbol", ".svg"]):
                            continue
                        srcset = item.get("srcset", [])
                        if srcset:
                            best_src = srcset[-1]["src"]
                            if best_src.startswith("//"):
                                best_src = "https:" + best_src
                            image_urls.append(best_src)

                if image_urls:
                    chosen_url = image_urls[scene_index % len(image_urls)]
                    logger.info(f"Downloading official BTS photo from '{page}': {chosen_url[:65]}...")
                    dl = requests.get(chosen_url, headers=HTTP_HEADERS, timeout=12)
                    if dl.status_code == 200 and len(dl.content) > 10000:
                        img_bytes = dl.content
                        break

            # 2. Fallback to page summary image
            summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(page)}"
            sr = requests.get(summary_url, headers=HTTP_HEADERS, timeout=8)
            if sr.status_code == 200:
                sdata = sr.json()
                img_url = sdata.get("thumbnail", {}).get("source") or sdata.get("originalimage", {}).get("source")
                if img_url:
                    logger.info(f"Downloading summary BTS photo from '{page}'...")
                    dl = requests.get(img_url, headers=HTTP_HEADERS, timeout=12)
                    if dl.status_code == 200 and len(dl.content) > 10000:
                        img_bytes = dl.content
                        break
        except Exception as e:
            logger.warning(f"Error fetching image for '{page}': {e}")
            continue

    if not img_bytes:
        return None

    try:
        orig = Image.open(BytesIO(img_bytes)).convert("RGB")
        w, h = orig.size

        # 1. Background: Blurred full 1080x1920 fill
        bg_scale = max(1080 / w, 1920 / h)
        bg_w, bg_h = int(w * bg_scale), int(h * bg_scale)
        bg = orig.resize((bg_w, bg_h), Image.Resampling.LANCZOS)
        left = (bg_w - 1080) // 2
        top = (bg_h - 1920) // 2
        bg = bg.crop((left, top, left + 1080, top + 1920))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=28))

        # BTS Purple aesthetic tint
        tint = Image.new("RGBA", (1080, 1920), (35, 10, 50, 115))
        bg = Image.alpha_composite(bg.convert("RGBA"), tint).convert("RGB")

        # 2. Foreground: Sharp photo centered in upper/middle canvas
        # (under top hook text, above bottom karaoke text)
        fg_scale = min(1000 / w, 1050 / h)
        fg_w, fg_h = int(w * fg_scale), int(h * fg_scale)
        fg = orig.resize((fg_w, fg_h), Image.Resampling.LANCZOS)

        fg_x = (1080 - fg_w) // 2
        fg_y = 270 + (1050 - fg_h) // 2
        bg.paste(fg, (fg_x, fg_y))

        # Draw gold accent border
        draw = ImageDraw.Draw(bg)
        draw.rectangle(
            [fg_x - 4, fg_y - 4, fg_x + fg_w + 4, fg_y + fg_h + 4],
            outline=(244, 208, 63), width=5
        )

        bg.save(dest_path, "JPEG", quality=95)
        logger.info(f"✅ Generated real BTS photo scene -> {dest_path}")
        return dest_path
    except Exception as e:
        logger.warning(f"Failed to format photo: {e}")
        return None


def create_fallback_scene_image(text_label: str, keyword: str, dest_path: Path) -> Path:
    """Generate high-res procedural 9:16 visual asset when stock/photo API is unavailable."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1080, 1920

    is_bts = any(w in (text_label + " " + keyword).lower() for w in ["bts", "army", "jungkook", "jimin", "jin", "suga", "rm", "v", "kpop", "bangtan", "purple"])

    if is_bts:
        bg_color = (25, 10, 40)
        circle_color = (110, 45, 150)
        box_fill = (45, 20, 70)
        border_gold = (244, 208, 63)
    else:
        bg_color = (15, 20, 30)
        circle_color = (40, 60, 90)
        box_fill = (25, 35, 55)
        border_gold = (212, 175, 55)

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    for r in range(400, 100, -50):
        draw.ellipse([width//2 - r, height//2 - r, width//2 + r, height//2 + r],
                     outline=circle_color, width=4)

    draw.rectangle([80, height//2 - 200, width - 80, height//2 + 200],
                   fill=box_fill, outline=border_gold, width=4)

    try:
        font_lg = ImageFont.truetype("arial.ttf", 52)
        font_sm = ImageFont.truetype("arial.ttf", 36)
    except IOError:
        font_lg = ImageFont.load_default()
        font_sm = ImageFont.load_default()

    draw.text((width//2, height//2 - 60), keyword.upper(), fill=border_gold, font=font_lg, anchor="mm")

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


BTS_NEWS_FEEDS = [
    "https://www.soompi.com/tag/bts/feed",
    "https://www.soompi.com/tag/jungkook/feed",
    "https://www.soompi.com/tag/jin/feed",
    "https://www.soompi.com/tag/jimin/feed",
    "https://www.soompi.com/tag/v/feed",
    "https://www.soompi.com/tag/suga/feed",
    "https://www.soompi.com/tag/rm/feed",
    "https://www.soompi.com/tag/j-hope/feed",
]


def fetch_latest_bts_article(output_dir: Path) -> Optional[dict]:
    """
    Select the newest usable headline/excerpt from free BTS RSS feeds and fetch
    its publisher preview image for the opening scene when one is available.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    import xml.etree.ElementTree as ET
    from html import unescape

    candidates = []
    history_path = output_dir / "content_history.json"
    try:
        history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else {}
    except (OSError, ValueError):
        history = {}
    cutoff_history = datetime.now().astimezone() - timedelta(days=30)
    seen_urls = {
        row.get("article_url") for row in history.get("items", [])
        if row.get("article_url") and row.get("used_at")
        and datetime.fromisoformat(row["used_at"]).astimezone() >= cutoff_history
    }
    cutoff = datetime.now().astimezone() - timedelta(days=3)
    for feed_url in BTS_NEWS_FEEDS:
        try:
            response = requests.get(feed_url, headers=HTTP_HEADERS, timeout=10)
            if response.status_code != 200:
                continue
            root = ET.fromstring(response.text)
            for item in root.findall(".//item")[:12]:
                title = unescape((item.findtext("title") or "").strip())
                link = (item.findtext("link") or "").strip()
                raw_description = item.findtext("description") or ""
                image_match = re.search(
                    r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']",
                    raw_description,
                    re.IGNORECASE,
                )
                image_url = image_match.group(1) if image_match else None
                if not image_url:
                    for media in item.iter():
                        local_tag = media.tag.rsplit("}", 1)[-1].lower()
                        candidate_url = media.attrib.get("url") or media.attrib.get("href")
                        if local_tag in {"content", "thumbnail", "enclosure"} and candidate_url:
                            image_url = candidate_url
                            break
                excerpt = unescape(re.sub(r"<[^>]+>", " ", raw_description))
                excerpt = re.sub(r"\s+", " ", excerpt).strip()[:1200]
                pub_text = item.findtext("pubDate") or ""
                if not title or not link:
                    continue
                try:
                    published = parsedate_to_datetime(pub_text).astimezone()
                except (TypeError, ValueError, OverflowError):
                    continue
                if published < cutoff or published > datetime.now().astimezone() + timedelta(hours=6):
                    continue
                if not re.search(r"\b(BTS|Bangtan|Jungkook|Jimin|Jin|Suga|Yoongi|RM|Namjoon|J-Hope|Hobi|V|Taehyung)\b", title, re.I):
                    continue
                if link in seen_urls:
                    continue
                candidates.append({"title": title, "description": excerpt, "article_url": link,
                    "published_at": published.isoformat(), "source": "Soompi",
                    "article_image_url": image_url})
        except Exception as error:
            logger.warning(f"Could not read BTS RSS feed {feed_url}: {error}")

    if not candidates:
        logger.warning("No recent, unused BTS source item found in the last 3 days.")
        return None
    candidates.sort(key=lambda item: item["published_at"], reverse=True)
    selected = candidates[0]
    local_image = fetch_article_preview_image(
        selected["article_url"], output_dir,
        rss_image_url=selected.get("article_image_url"),
    )
    if local_image:
        selected["local_image_path"] = str(local_image)
    logger.info(f"Selected newest source item: {selected['title'][:100]} ({selected['article_url']})")
    history.setdefault("items", []).append({
        "article_url": selected["article_url"],
        "title": selected["title"],
        "used_at": datetime.now().astimezone().isoformat(),
    })
    history["items"] = history["items"][-100:]
    output_dir.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return selected


class _ArticlePreviewParser(HTMLParser):
    """Read social preview image URLs from common article metadata tags."""

    def __init__(self):
        super().__init__()
        self.image_url = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta":
            return
        values = {key.lower(): value for key, value in attrs if key and value}
        property_name = (values.get("property") or values.get("name") or "").lower()
        if property_name in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}:
            if values.get("content"):
                self.image_url = values["content"].strip()


def fetch_article_preview_image(
    article_url: str,
    output_dir: Path,
    rss_image_url: Optional[str] = None,
) -> Optional[Path]:
    """Download and format the image advertised by an article's social metadata."""
    image_url = rss_image_url
    try:
        page = requests.get(article_url, headers=HTTP_HEADERS, timeout=15)
        page.raise_for_status()
        parser = _ArticlePreviewParser()
        parser.feed(page.text)
        if parser.image_url:
            image_url = urljoin(page.url, parser.image_url)
    except Exception as error:
        logger.warning(f"Could not read article social image metadata: {error}")

    if not image_url:
        logger.warning("Article page and RSS item did not provide a preview image.")
        return None

    try:
        image_url = urljoin(article_url, image_url)
        if not image_url.startswith(("https://", "http://")):
            logger.warning("Ignoring unsupported article image URL scheme.")
            return None

        response = requests.get(image_url, headers=HTTP_HEADERS, timeout=20, stream=True)
        response.raise_for_status()
        max_bytes = 15 * 1024 * 1024
        chunks = []
        size = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("Article image exceeds the 15 MB download limit")
            chunks.append(chunk)

        image_bytes = b"".join(chunks)
        with Image.open(BytesIO(image_bytes)) as image:
            image_format = (image.format or "JPEG").upper()
            image.verify()
        extension = {"JPEG": ".jpg", "JPG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(image_format)
        if not extension:
            logger.warning(f"Unsupported article image format: {image_format}")
            return None

        dest_path = output_dir / f"article_image{extension}"
        dest_path.write_bytes(image_bytes)
        logger.info(f"Saved original article preview image unchanged -> {dest_path}")
        return dest_path
    except Exception as error:
        logger.warning(f"Could not fetch article preview image: {error}")
        return None


def fetch_multi_scene_content(
    script_data: dict,
    output_dir: Path,
    source_content: Optional[dict] = None,
) -> List[dict]:
    """
    Use the publisher image as the opening scene, then make a unique editorial
    card for each sentence so one downloaded photo is not repeated throughout.
    """
    scenes_dir = output_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    pexels_key = os.environ.get("PEXELS_API_KEY", "").strip()
    is_bts = script_data.get("niche", "bts") == "bts"
    article_image_path = None
    if is_bts and source_content and source_content.get("local_image_path"):
        candidate = Path(source_content["local_image_path"])
        if candidate.is_file():
            article_image_path = candidate
    if is_bts and not article_image_path:
        raise RuntimeError("A downloaded article image is required for BTS scenes.")

    sentences = script_data.get("sentences", [])

    if not sentences:
        narration = script_data.get("narration", "BTS World Records")
        sentences = [{"text": narration, "keywords": [script_data.get("title_keyword", "BTS")]}]

    scenes_meta = []

    for i, s in enumerate(sentences):
        text = s.get("text", "")
        keywords = s.get("keywords", ["BTS"])
        kw = keywords[0] if keywords else "BTS"

        video_dest = scenes_dir / f"scene_{i}.mp4"
        image_dest = scenes_dir / f"scene_{i}.jpg"

        fetched_path = None
        media_type = "image"

        if is_bts:
            if i == 0:
                fetched_path = article_image_path
            else:
                fetched_path = create_fallback_scene_image(text, kw, image_dest)
            media_type = "image"

        # Non-BTS legacy niches may use licensed/authorized external stock.
        if not fetched_path and pexels_key:
            try:
                fetched_path = fetch_pexels_video(kw, pexels_key, video_dest)
                if fetched_path:
                    media_type = "video"
            except Exception as e:
                logger.warning(f"Pexels fetch failed for '{kw}': {e}")

        # 2. Procedural card fallback if network is offline
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
    api_key = api_key or os.environ.get("NASA_API_KEY") or "DEMO_KEY"
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
        json.dump(data, f, indent=2)


_DRY_RUN_SCENES = [
    {
        "scene_index": 0,
        "text": "Did you know BTS holds over thirty Guinness World Records?",
        "keyword": "stadium concert crowd",
        "media_path": "output/scenes/scene_0.jpg",
        "media_type": "image"
    },
    {
        "scene_index": 1,
        "text": "They became the first group in history to hold multiple Billboard number-one debuts.",
        "keyword": "music award trophy",
        "media_path": "output/scenes/scene_1.jpg",
        "media_type": "image"
    },
    {
        "scene_index": 2,
        "text": "Their global impact inspired millions and brought Korean music to the United Nations.",
        "keyword": "united nations assembly",
        "media_path": "output/scenes/scene_2.jpg",
        "media_type": "image"
    },
    {
        "scene_index": 3,
        "text": "Subscribe for daily BTS updates and ARMY facts! 💜",
        "keyword": "purple lights crowd",
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
        raise FileNotFoundError(f"Script file not found: {script_path}")

    scenes_meta = fetch_multi_scene_content(script_data, output_dir)
    print(json.dumps({"scenes": scenes_meta}, indent=2))


if __name__ == "__main__":
    main()
