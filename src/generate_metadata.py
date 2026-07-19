"""
generate_metadata.py — Step 5 of The Universe pipeline.

Produces YouTube upload metadata:
  - Title (< 60 chars, hook keyword front-loaded)
  - Description (1–2 sentence summary + hashtags)
  - Tags array (up to 15)
  - Category ID: 28 (Science & Technology)
  - Privacy, madeForKids, containsSyntheticMedia flags

Usage:
    python src/generate_metadata.py --apod output/apod.json --script output/script.json
    python src/generate_metadata.py --dry-run
"""

import argparse
import json
import logging
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("generate_metadata")

# ── Hashtag pools ──────────────────────────────────────────────────────────────
HASHTAGS_BROAD = ["#space", "#nasa", "#shorts", "#science", "#universe", "#astronomy"]
HASHTAGS_NICHE = ["#apod", "#spacefacts", "#cosmos", "#astrophotography", "#deepspace", "#nasapics", "#spacewatch"]
HASHTAGS_VIRAL = ["#mindblowing", "#didyouknow", "#amazingfacts", "#todayinspace", "#scienceisawesome"]

# Tag pool (no # prefix for YouTube tags array)
TAGS_BASE = [
    "space", "nasa", "astronomy", "universe", "cosmos", "astrophotography",
    "space facts", "science shorts", "today in space", "apod", "youtube shorts",
    "deep space", "nasa image", "space science", "stellar",
]


def _build_title(keyword: str, apod_title: str, content_type: str = "apod") -> str:
    """
    Build a YouTube title < 60 chars with hook keyword front-loaded.
    Format: "{Keyword}: {Punchy phrase} #Shorts"
    """
    if content_type == "asteroid_watch":
        title = f"🌑 Asteroid Watch: {keyword} This Week #Shorts"
    else:
        # Truncate apod_title if needed
        truncated = apod_title if len(apod_title) <= 30 else apod_title[:27] + "..."
        candidates = [
            f"🌌 {keyword}: {truncated} #Shorts",
            f"🔭 {truncated} | NASA APOD #Shorts",
            f"🌌 {keyword} Explained in 20s #Shorts",
        ]
        # Pick the one that fits under 60 chars (prefer first)
        title = next((c for c in candidates if len(c) <= 60), candidates[-1][:60])

    logger.info(f"Generated title ({len(title)} chars): {title}")
    return title


def _build_description(
    narration: str,
    apod_date: str,
    apod_title: str,
    copyright_holder: str,
    hashtags: list[str],
    content_type: str = "apod",
) -> str:
    """Build a compelling 3-4 sentence description with hashtags."""
    date_fmt = ""
    if apod_date:
        try:
            dt = datetime.strptime(apod_date, "%Y-%m-%d")
            date_fmt = dt.strftime("%B %d, %Y")
        except ValueError:
            date_fmt = apod_date

    if content_type == "asteroid_watch":
        summary = (
            f"This week's Asteroid Watch — tracking near-Earth objects with NASA data. "
            f"All statistics sourced directly from NASA's NEO API. No dramatisation."
        )
    else:
        summary = (
            f"Today's NASA Astronomy Picture of the Day: {apod_title} ({date_fmt}). "
            f"Image credit: {copyright_holder}. "
            f"All facts sourced directly from NASA APOD — no AI-generated imagery."
        )

    hashtag_str = " ".join(hashtags)
    desc = (
        f"{summary}\n\n"
        f"🔔 Follow @TheUniverseChannel for daily space facts.\n\n"
        f"📸 Source: NASA APOD — https://apod.nasa.gov\n\n"
        f"{hashtag_str}"
    )
    logger.info(f"Description built ({len(desc)} chars)")
    return desc


def _build_hashtags(keyword: str, content_type: str = "apod") -> list[str]:
    """Select a balanced set of hashtags (max 6 in description)."""
    selected = []
    # Always include these
    selected += ["#space", "#nasa", "#shorts"]

    # Add keyword-specific niche tag
    kw_tag = "#" + re.sub(r"\s+", "", keyword.lower())
    if kw_tag not in selected and len(kw_tag) < 25:
        selected.append(kw_tag)

    if content_type == "asteroid_watch":
        selected.append("#asteroidwatch")
    else:
        selected.append("#apod")

    # Fill up to 6 from viral pool
    remaining = [h for h in HASHTAGS_VIRAL if h not in selected]
    random.shuffle(remaining)
    selected += remaining[:max(0, 6 - len(selected))]

    return selected[:6]


def _build_tags(keyword: str, apod_title: str, content_type: str = "apod") -> list[str]:
    """Build the YouTube tags array (no # prefix), max 15 tags."""
    tags = list(TAGS_BASE)

    # Add keyword as explicit tag
    kw_clean = keyword.lower().strip()
    if kw_clean not in tags:
        tags.insert(0, kw_clean)

    # Add significant words from apod title
    title_words = [w.lower() for w in apod_title.split() if len(w) > 4]
    for w in title_words[:3]:
        if w not in tags:
            tags.append(w)

    if content_type == "asteroid_watch":
        tags = ["asteroid", "near earth object", "nasa neo", "asteroid watch"] + tags

    return tags[:15]


def generate_metadata(
    apod_data: dict,
    script_data: dict,
) -> dict:
    """
    Generate complete YouTube upload metadata.
    Returns the metadata dict ready for upload_video.py.
    """
    keyword = script_data.get("title_keyword", "Space")
    narration = script_data.get("narration", "")
    hook_text = script_data.get("hook_text", "")
    content_type = script_data.get("content_type", "apod")

    apod_title = apod_data.get("title", "NASA Astronomy Picture of the Day")
    apod_date = apod_data.get("date", "")
    copyright_holder = apod_data.get("copyright", "NASA")

    title = _build_title(keyword, apod_title, content_type)
    hashtags = _build_hashtags(keyword, content_type)
    description = _build_description(
        narration, apod_date, apod_title, copyright_holder, hashtags, content_type
    )
    tags = _build_tags(keyword, apod_title, content_type)

    metadata = {
        "title": title,
        "description": description,
        "tags": tags,
        "hashtags": hashtags,
        "categoryId": "28",                   # Science & Technology
        "privacyStatus": "public",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": False,       # Real NASA imagery + human script
        "defaultLanguage": "en",
        "content_type": content_type,
        "apod_date": apod_date,
    }

    logger.info(f"Metadata generated: title='{title}', tags={len(tags)}, hashtags={len(hashtags)}")
    return metadata


# ── DRY RUN fixture ────────────────────────────────────────────────────────────
_DRY_RUN_METADATA = {
    "title": "🌌 Orion Nebula: Stars Being Born #Shorts",
    "description": "Today's NASA Astronomy Picture of the Day...\n\n#space #nasa #shorts",
    "tags": ["orion nebula", "space", "nasa", "astronomy"],
    "hashtags": ["#space", "#nasa", "#shorts", "#apod"],
    "categoryId": "28",
    "privacyStatus": "public",
    "selfDeclaredMadeForKids": False,
    "containsSyntheticMedia": False,
    "defaultLanguage": "en",
    "dry_run": True,
}


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Generate YouTube metadata for The Universe Shorts.")
    parser.add_argument("--apod", default="output/apod.json")
    parser.add_argument("--script", default="output/script.json")
    parser.add_argument("--output", default="output/metadata.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        with open(output_path, "w") as f:
            json.dump(_DRY_RUN_METADATA, f, indent=2)
        print(json.dumps(_DRY_RUN_METADATA, indent=2))
        return

    with open(args.apod) as f:
        apod_data = json.load(f)
    with open(args.script) as f:
        script_data = json.load(f)

    metadata = generate_metadata(apod_data, script_data)

    with open(output_path, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Metadata saved → {output_path}")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
