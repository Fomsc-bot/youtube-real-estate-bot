"""
fetch_content.py — Step 1 of The Universe pipeline.

Fetches NASA APOD (Astronomy Picture of the Day) data and downloads
the image to disk. Handles video-type APODs gracefully by fetching
the previous day's image instead.

Usage:
    python src/fetch_content.py --output output/
    python src/fetch_content.py --output output/ --date 2024-07-04
    python src/fetch_content.py --dry-run
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fetch_content")

# ── Config ─────────────────────────────────────────────────────────────────────
APOD_URL = "https://api.nasa.gov/planetary/apod"
NEO_URL = "https://api.nasa.gov/neo/rest/v1/feed"
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".tiff", ".webp"}
MAX_FALLBACK_DAYS = 7   # How many days back to look if today is a video


# ── Retry decorator ────────────────────────────────────────────────────────────
def _make_retry():
    return retry(
        retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.Timeout)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


@_make_retry()
def _get_apod(api_key: str, date: Optional[str] = None) -> dict:
    """Call APOD API and return the JSON response dict."""
    params = {"api_key": api_key, "thumbs": True}  # thumbs=True gives thumbnail for videos
    if date:
        params["date"] = date

    logger.info(f"Calling APOD API for date={date or 'today'} ...")
    resp = requests.get(APOD_URL, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    logger.info(f"APOD response: title='{data.get('title')}', media_type='{data.get('media_type')}'")
    return data


@_make_retry()
def _download_image(url: str, dest_path: Path) -> Path:
    """Download image from URL to dest_path."""
    logger.info(f"Downloading image from {url} → {dest_path}")
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
    size_kb = dest_path.stat().st_size // 1024
    logger.info(f"Image saved to {dest_path} ({size_kb} KB)")
    return dest_path


def _image_ext_from_url(url: str) -> str:
    """Extract the file extension from a URL, default to .jpg."""
    path = urlparse(url).path
    ext = Path(path).suffix.lower()
    return ext if ext in SUPPORTED_IMAGE_EXTENSIONS else ".jpg"


def fetch_apod(api_key: str, output_dir: Path, date: Optional[str] = None) -> dict:
    """
    Fetch APOD data. If today's APOD is a video, walk back up to
    MAX_FALLBACK_DAYS until we find an image.

    Returns a metadata dict ready to be saved as apod.json.
    """
    check_date = date  # None = today

    for attempt in range(MAX_FALLBACK_DAYS + 1):
        data = _get_apod(api_key, date=check_date)
        media_type = data.get("media_type", "image")

        if media_type == "image":
            image_url = data["url"]
            hdurl = data.get("hdurl", image_url)
            ext = _image_ext_from_url(hdurl)
            dest = output_dir / f"apod_image{ext}"
            _download_image(hdurl, dest)

            result = {
                "date": data.get("date"),
                "title": data.get("title", ""),
                "explanation": data.get("explanation", ""),
                "url": image_url,
                "hdurl": hdurl,
                "media_type": "image",
                "local_image_path": str(dest),
                "copyright": data.get("copyright", "NASA"),
                "fetched_at": datetime.utcnow().isoformat() + "Z",
            }
            logger.info(f"Successfully fetched image APOD: '{result['title']}'")
            return result

        elif media_type == "video":
            # APOD returned a video (usually YouTube embed).
            # Try to use the thumbnail URL if available, else fall back a day.
            thumb = data.get("thumbnail_url")
            if thumb and attempt == 0:
                logger.warning(
                    f"APOD is a video today. Using provided thumbnail: {thumb}"
                )
                ext = _image_ext_from_url(thumb)
                dest = output_dir / f"apod_image{ext}"
                _download_image(thumb, dest)

                result = {
                    "date": data.get("date"),
                    "title": data.get("title", ""),
                    "explanation": data.get("explanation", ""),
                    "url": data.get("url", ""),
                    "hdurl": thumb,
                    "media_type": "video_thumbnail",
                    "local_image_path": str(dest),
                    "copyright": data.get("copyright", "NASA"),
                    "fetched_at": datetime.utcnow().isoformat() + "Z",
                }
                logger.info(f"Using video thumbnail for APOD: '{result['title']}'")
                return result

            # Fall back to the previous day
            if check_date is None:
                check_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                prev = datetime.strptime(check_date, "%Y-%m-%d") - timedelta(days=1)
                check_date = prev.strftime("%Y-%m-%d")
            logger.warning(
                f"APOD on {data.get('date')} is a video with no thumbnail. "
                f"Trying {check_date} ..."
            )

    raise RuntimeError(
        f"Could not find an image-based APOD within {MAX_FALLBACK_DAYS} days."
    )


@_make_retry()
def fetch_neo_week(api_key: str, output_dir: Path) -> dict:
    """
    Fetch NASA NEO feed for the current week (7 days).
    Returns a summary dict with the top asteroid facts.
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")
    end = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
    logger.info(f"Fetching NEO feed {today} → {end} ...")
    resp = requests.get(
        NEO_URL,
        params={"start_date": today, "end_date": end, "api_key": api_key},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    all_neos = []
    for date_str, neos in data.get("near_earth_objects", {}).items():
        for neo in neos:
            max_diam_km = neo.get("estimated_diameter", {}).get("kilometers", {}).get("estimated_diameter_max", 0)
            miss_km = None
            for approach in neo.get("close_approach_data", []):
                miss_km = float(approach.get("miss_distance", {}).get("kilometers", 0))
                break
            all_neos.append({
                "name": neo.get("name", "Unknown"),
                "date": date_str,
                "diameter_km": round(max_diam_km, 3),
                "miss_distance_km": round(miss_km, 0) if miss_km else None,
                "is_potentially_hazardous": neo.get("is_potentially_hazardous_asteroid", False),
            })

    # Sort by closest approach
    all_neos.sort(key=lambda x: x.get("miss_distance_km") or float("inf"))

    result = {
        "count": data.get("element_count", 0),
        "top_asteroid": all_neos[0] if all_neos else None,
        "hazardous_count": sum(1 for n in all_neos if n["is_potentially_hazardous"]),
        "all_neos": all_neos[:10],
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "content_type": "asteroid_watch",
    }
    logger.info(
        f"NEO fetch complete: {result['count']} objects this week, "
        f"{result['hazardous_count']} potentially hazardous."
    )
    return result


def save_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved metadata → {path}")


# ── DRY RUN fixture ────────────────────────────────────────────────────────────
_DRY_RUN_APOD = {
    "date": datetime.utcnow().strftime("%Y-%m-%d"),
    "title": "The Orion Nebula in Infrared",
    "explanation": (
        "The Orion Nebula is one of the most studied objects in the night sky. "
        "Located about 1,344 light-years away, it is a stellar nursery where new "
        "stars are forming from collapsing clouds of gas and dust. The Hubble Space "
        "Telescope has revealed thousands of young stellar objects embedded in this "
        "iconic cloud, making it a prime laboratory for understanding star formation."
    ),
    "url": "https://apod.nasa.gov/apod/image/2407/OrionNebula_Hubble_960.jpg",
    "hdurl": "https://apod.nasa.gov/apod/image/2407/OrionNebula_Hubble_2000.jpg",
    "media_type": "image",
    "local_image_path": "output/apod_image.jpg",
    "copyright": "NASA / ESA / Hubble",
    "fetched_at": datetime.utcnow().isoformat() + "Z",
    "dry_run": True,
}


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Fetch NASA APOD content for The Universe pipeline.")
    parser.add_argument("--output", default="output", help="Output directory for image and JSON")
    parser.add_argument("--date", default=None, help="Specific APOD date (YYYY-MM-DD)")
    parser.add_argument("--neo", action="store_true", help="Fetch NEO asteroid data instead of APOD")
    parser.add_argument("--dry-run", action="store_true", help="Skip real API calls; write fixture data")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        logger.info("DRY RUN mode — using fixture APOD data, no real API calls.")
        save_json(_DRY_RUN_APOD, output_dir / "apod.json")
        print(json.dumps(_DRY_RUN_APOD, indent=2))
        return

    api_key = os.environ.get("NASA_API_KEY", "").strip()
    if not api_key:
        api_key = "DEMO_KEY"
        logger.warning("NASA_API_KEY not set or empty — using DEMO_KEY (rate limited to 30/hour).")

    if args.neo:
        data = fetch_neo_week(api_key, output_dir)
        save_json(data, output_dir / "neo.json")
        print(json.dumps(data, indent=2))
    else:
        data = fetch_apod(api_key, output_dir, date=args.date)
        save_json(data, output_dir / "apod.json")
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
