"""Fetch reusable BTS photos from Wikimedia Commons with attribution data."""

import hashlib
import html
from io import BytesIO
import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path

import requests
from PIL import Image

logger = logging.getLogger("longform_assets")
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "BTSLongformCommentary/1.0 (source-attribution enabled)"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def _plain_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    return html.unescape(" ".join(parser.parts)).strip()


def _commercial_reuse_license(short_name: str) -> bool:
    name = (short_name or "").casefold()
    if "noncommercial" in name or "non-commercial" in name or "no derivatives" in name or "no-derivatives" in name:
        return False
    return ("cc by" in name and "by-sa" not in name and "by sa" not in name) or "cc0" in name or "public domain" in name


def fetch_longform_photos(output_dir: Path, count: int = 5) -> list[dict]:
    """Download distinct, commercially reusable BTS photos and save their credits."""
    output_dir.mkdir(parents=True, exist_ok=True)
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": "BTS",
        "gsrnamespace": 6,
        "gsrlimit": 50,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size",
        "iiurlwidth": 1920,
    }
    response = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {}).values()

    selected = []
    seen_digests = set()
    for page in pages:
        title = page.get("title", "")
        if not re.search(r"\b(BTS|Bangtan|RM|Jin|Suga|J.?Hope|Jimin|V|Jungkook)\b", title, re.I):
            continue
        if re.search(r"logo|album.?cover|poster|icon|screenshot|fan.?art", title, re.I):
            continue
        info_list = page.get("imageinfo", [])
        if not info_list:
            continue
        info = info_list[0]
        metadata = info.get("extmetadata", {})
        license_name = _plain_text(metadata.get("LicenseShortName", {}).get("value", ""))
        if not _commercial_reuse_license(license_name):
            continue
        image_url = info.get("thumburl") or info.get("url")
        if not image_url or not info.get("mime", "").startswith("image/"):
            continue

        try:
            image_response = requests.get(image_url, headers=HEADERS, timeout=30)
            image_response.raise_for_status()
            image_bytes = image_response.content
            digest = hashlib.sha256(image_bytes).hexdigest()
            if digest in seen_digests:
                continue
            with Image.open(BytesIO(image_bytes)) as image:
                image.verify()
            image_path = output_dir / f"commons_{digest[:12]}.jpg"
            with Image.open(BytesIO(image_bytes)) as image:
                image.convert("RGB").save(image_path, "JPEG", quality=92)
        except Exception as error:
            logger.warning("Skipping unusable Commons image %s: %s", title, error)
            continue

        artist = _plain_text(metadata.get("Artist", {}).get("value", "")) or "Unknown creator"
        credit = {
            "file": title.removeprefix("File:"),
            "creator": artist,
            "license": license_name,
            "license_url": _plain_text(metadata.get("LicenseUrl", {}).get("value", "")),
            "source_url": page.get("fullurl", "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_")),
            "local_path": str(image_path),
        }
        selected.append(credit)
        seen_digests.add(digest)
        logger.info("Downloaded reusable image: %s (%s)", credit["file"], license_name)
        if len(selected) >= count:
            break

    if len(selected) < count:
        raise RuntimeError(
            f"Found only {len(selected)} distinct CC BY/CC0/public-domain BTS images; "
            f"{count} are needed. Add properly licensed source images or reduce the chapter count."
        )

    (output_dir / "image_credits.json").write_text(
        json.dumps(selected, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return selected
