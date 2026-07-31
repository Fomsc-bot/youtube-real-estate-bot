"""
generate_metadata.py — High-CTR SEO & Subscriber Conversion Engine

Produces YouTube upload metadata:
  - High-CTR Title (< 60 chars with curiosity gap & front-loaded hook)
  - Rich Description + Pinned Comment Prompt (spurs comments & subscribers)
  - Optimized Tag Array (up to 15) & Hashtag Stack (#Shorts #RealEstate)

Usage:
    python src/generate_metadata.py --script output/script.json
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

HASHTAGS_REAL_ESTATE = ["#shorts", "#realestate", "#luxuryhomes", "#architecture", "#mansion", "#luxury"]
HASHTAGS_SPACE = ["#shorts", "#space", "#nasa", "#astronomy", "#spacefacts", "#universe"]
HASHTAGS_VIRAL = ["#mindblowing", "#didyouknow", "#amazingfacts", "#viral", "#luxurylifestyle"]


def _build_title(keyword: str, hook_text: str, niche: str = "real_estate") -> str:
    """Build a high-CTR YouTube title (< 60 chars)."""
    if niche == "real_estate":
        emoji = random.choice(["🏡", "🏰", "🔑", "✨", "💰"])
        candidates = [
            f"{emoji} {hook_text} #Shorts",
            f"{emoji} {keyword}: Secrets Exposed #Shorts",
            f"🏡 Inside {hook_text} | Luxury Tour #Shorts",
        ]
    else:
        emoji = random.choice(["🌌", "🔭", "💫", "🚀", "🪐"])
        candidates = [
            f"{emoji} {hook_text} #Shorts",
            f"{emoji} {keyword} Explained #Shorts",
            f"🌌 Deep Space: {hook_text} #Shorts",
        ]

    title = next((c for c in candidates if len(c) <= 60), candidates[0][:60])
    logger.info(f"Generated High-CTR Title ({len(title)} chars): {title}")
    return title


def _build_description(
    narration: str,
    keyword: str,
    hashtags: list[str],
    niche: str = "real_estate",
) -> str:
    """Build subscriber-converting description and pinned comment prompt."""
    if niche == "real_estate":
        cta_prompt = "🔔 Hit SUBSCRIBE for daily luxury real estate tours, mega mansions & architectural secrets!"
        comment_prompt = "💬 QUESTION: Which feature of this property would you add to your dream house? Comment below!"
    else:
        cta_prompt = "🔔 Hit SUBSCRIBE for daily mind-blowing space facts and cosmic discoveries!"
        comment_prompt = "💬 QUESTION: What space mystery fascinates you the most? Comment below!"

    hashtag_str = " ".join(hashtags)
    desc = (
        f"{narration[:180]}...\n\n"
        f"{cta_prompt}\n\n"
        f"{comment_prompt}\n\n"
        f"{hashtag_str}"
    )
    return desc


def _build_hashtags(keyword: str, niche: str = "real_estate") -> list[str]:
    """Select a balanced set of 6 viral hashtags."""
    pool = HASHTAGS_REAL_ESTATE if niche == "real_estate" else HASHTAGS_SPACE
    selected = list(pool[:4])

    kw_tag = "#" + re.sub(r"\s+", "", keyword.lower())
    if kw_tag not in selected and len(kw_tag) < 22:
        selected.append(kw_tag)

    remaining = [h for h in HASHTAGS_VIRAL if h not in selected]
    random.shuffle(remaining)
    selected += remaining[:max(0, 6 - len(selected))]
    return selected[:6]


def _build_tags(keyword: str, niche: str = "real_estate") -> list[str]:
    """Build YouTube tags array (max 15 tags)."""
    if niche == "real_estate":
        base_tags = [
            "real estate", "luxury real estate", "mansion", "mega mansion",
            "house tour", "architecture", "home design", "luxury home",
            "property tour", "shorts", "youtube shorts", "luxury lifestyle"
        ]
    else:
        base_tags = [
            "space", "astronomy", "nasa", "universe", "cosmos",
            "space facts", "astrophotography", "shorts", "youtube shorts"
        ]

    kw_clean = keyword.lower().strip()
    if kw_clean not in base_tags:
        base_tags.insert(0, kw_clean)

    return base_tags[:15]


def generate_metadata(script_data: dict, apod_data: Optional[dict] = None) -> dict:
    """Generate YouTube upload metadata dict."""
    keyword = script_data.get("title_keyword", "Luxury Mansion")
    narration = script_data.get("narration", "")
    hook_text = script_data.get("hook_text", "Luxury Real Estate")
    niche = script_data.get("niche", "real_estate")

    title = _build_title(keyword, hook_text, niche)
    hashtags = _build_hashtags(keyword, niche)
    description = _build_description(narration, keyword, hashtags, niche)
    tags = _build_tags(keyword, niche)
    category_id = "24" if niche == "real_estate" else "28"

    metadata = {
        "title": title,
        "description": description,
        "tags": tags,
        "hashtags": hashtags,
        "categoryId": category_id,
        "privacyStatus": "public",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": False,
        "defaultLanguage": "en",
        "niche": niche,
        "pinned_comment": "Which feature of this tour surprised you the most? Hit SUBSCRIBE & comment below! 👇",
    }

    logger.info(f"Metadata generated: title='{title}', tags={len(tags)}")
    return metadata


# ── DRY RUN ────────────────────────────────────────────────────────────────────
_DRY_RUN_METADATA = {
    "title": "🏡 Inside $100M Mega Mansion #Shorts",
    "description": "Inside this $100 Million Mega Mansion...\n\n#shorts #realestate #luxuryhomes",
    "tags": ["real estate", "luxury real estate", "mansion"],
    "hashtags": ["#shorts", "#realestate", "#luxuryhomes"],
    "categoryId": "24",
    "privacyStatus": "public",
    "selfDeclaredMadeForKids": False,
    "containsSyntheticMedia": False,
    "defaultLanguage": "en",
    "niche": "real_estate",
    "pinned_comment": "Which feature of this tour surprised you the most? Hit SUBSCRIBE & comment below! 👇",
    "dry_run": True,
}


def main():
    parser = argparse.ArgumentParser(description="Generate viral YouTube metadata.")
    parser.add_argument("--script", default="output/script.json")
    parser.add_argument("--output", default="output/metadata.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(_DRY_RUN_METADATA, f, indent=2)
        print(json.dumps(_DRY_RUN_METADATA, indent=2))
        return

    with open(args.script, encoding="utf-8") as f:
        script_data = json.load(f)

    metadata = generate_metadata(script_data)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Metadata saved -> {output_path}")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
