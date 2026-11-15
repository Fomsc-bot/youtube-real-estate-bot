"""
generate_metadata.py — High-CTR SEO & Subscriber Conversion Engine

Produces YouTube upload metadata:
  - High-CTR Title (< 60 chars with curiosity gap & front-loaded hook)
  - Rich Description + Pinned Comment Prompt (spurs comments & subscribers)
  - Optimized Tag Array (up to 15) & Hashtag Stack (#Shorts #BTS #BTSARMY)

Usage:
    python src/generate_metadata.py --script output/script.json
    python src/generate_metadata.py --dry-run
"""

import argparse
import json
import logging
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

HASHTAGS_BTS = ["#shorts", "#BTS", "#BTSARMY", "#Bangtan", "#kpop", "#BTSUpdates", "#RM", "#Jin", "#SUGA", "#JHope", "#Jimin", "#V", "#Jungkook"]
HASHTAGS_REAL_ESTATE = ["#shorts", "#realestate", "#luxuryhomes", "#architecture", "#mansion", "#luxury"]
HASHTAGS_SPACE = ["#shorts", "#space", "#nasa", "#astronomy", "#spacefacts", "#universe"]
HASHTAGS_VIRAL = ["#mindblowing", "#didyouknow", "#amazingfacts", "#viral", "#btsforever"]


def _build_title(keyword: str, hook_text: str, niche: str = "bts", suggested_title: str = "") -> str:
    """Use a specific, accurate title; avoid random emoji/hashtag padding."""
    if niche == "bts":
        title = re.sub(r"\s+", " ", suggested_title or keyword).strip(" -|#")
        if not re.search(r"\bBTS\b", title, re.I):
            title = f"{title} | BTS"
        return title[:60].rstrip(" -|")
    elif niche == "real_estate":
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
    niche: str = "bts",
    source_publisher: str = "",
    source_url: str = "",
    viewer_question: str = "",
) -> str:
    """Build subscriber-converting description and pinned comment prompt."""
    if niche == "bts":
        cta_prompt = "Independent fan commentary. Subscribe for source-checked BTS stories and context."
        comment_prompt = viewer_question.strip()
    elif niche == "real_estate":
        cta_prompt = "🔔 Hit SUBSCRIBE for daily luxury real estate tours, mega mansions & architectural secrets!"
        comment_prompt = "💬 QUESTION: Which feature of this property would you add to your dream house? Comment below!"
    else:
        cta_prompt = "🔔 Hit SUBSCRIBE for daily mind-blowing space facts and cosmic discoveries!"
        comment_prompt = "💬 QUESTION: What space mystery fascinates you the most? Comment below!"

    hashtag_str = " ".join(hashtags)
    parts = [narration[:220].strip()]
    if niche == "bts" and source_url:
        parts.append(f"Source report ({source_publisher or 'publisher'}): {source_url}")
    parts.extend(part for part in [cta_prompt, comment_prompt, hashtag_str] if part)
    desc = "\n\n".join(parts)
    return desc


def _build_hashtags(keyword: str, niche: str = "bts") -> list[str]:
    """Use only a few relevant hashtags rather than generic viral tags."""
    if niche == "bts":
        member_tags = {"rm": "#RM", "jin": "#Jin", "suga": "#SUGA", "j-hope": "#JHope", "jhope": "#JHope", "jimin": "#Jimin", "v": "#V", "taehyung": "#V", "jungkook": "#Jungkook"}
        selected = ["#BTS", "#Shorts"]
        for name, tag in member_tags.items():
            if re.search(rf"\b{re.escape(name)}\b", keyword, re.I) and tag not in selected:
                selected.insert(1, tag)
                break
        return selected
    elif niche == "real_estate":
        pool = HASHTAGS_REAL_ESTATE
    else:
        pool = HASHTAGS_SPACE

    selected = list(pool[:4])

    kw_tag = "#" + re.sub(r"\s+", "", keyword.lower())
    if kw_tag not in selected and len(kw_tag) < 22:
        selected.append(kw_tag)

    return selected[:3]


def _build_tags(keyword: str, niche: str = "bts") -> list[str]:
    """Build YouTube tags array (max 15 tags)."""
    if niche == "bts":
        base_tags = [
            "bts", "bts army", "bangtan sonyeondan", "bangtan",
            "kpop", "rm", "jin", "suga", "j-hope", "jimin", "v",
            "jungkook", "bts shorts", "bts updates", "bts facts"
        ]
    elif niche == "real_estate":
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
    keyword = script_data.get("title_keyword", "BTS Spotlight")
    narration = script_data.get("narration", "")
    hook_text = script_data.get("hook_text", "BTS World Records")
    niche = script_data.get("niche", "bts")

    title = _build_title(keyword, hook_text, niche, script_data.get("title", ""))
    hashtags = _build_hashtags(keyword, niche)
    description = _build_description(narration, keyword, hashtags, niche,
        script_data.get("source_publisher", ""), script_data.get("source_url", ""),
        script_data.get("viewer_question", ""))
    tags = _build_tags(keyword, niche)

    # Category 10 = Music (BTS), 24 = Entertainment (Real Estate), 28 = Science (Space)
    if niche == "bts":
        category_id = "10"
        viewer_prompt = script_data.get("viewer_question") or "What BTS story should we put in context next?"
    elif niche == "real_estate":
        category_id = "24"
        viewer_prompt = "Which feature of this tour surprised you the most? Hit SUBSCRIBE & comment below! 👇"
    else:
        category_id = "28"
        viewer_prompt = "What space mystery fascinates you the most? Hit SUBSCRIBE & comment below! 👇"

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
        "viewer_prompt": viewer_prompt,
    }

    logger.info(f"Metadata generated: title='{title}', tags={len(tags)}")
    return metadata


# ── DRY RUN ────────────────────────────────────────────────────────────────────
_DRY_RUN_METADATA = {
    "title": "💜 BTS Historic World Record #Shorts",
    "description": "Did you know BTS holds over thirty Guinness World Records?...\n\n🔔 Hit SUBSCRIBE for daily BTS updates! 💜",
    "tags": ["bts", "bts army", "bangtan", "kpop", "rm", "jin", "suga", "jhope", "jimin", "v", "jungkook"],
    "hashtags": ["#shorts", "#BTS", "#BTSARMY", "#Bangtan", "#kpop", "#BTSUpdates"],
    "categoryId": "10",
    "privacyStatus": "public",
    "selfDeclaredMadeForKids": False,
    "containsSyntheticMedia": False,
    "defaultLanguage": "en",
    "niche": "bts",
    "viewer_prompt": "What BTS story should we put in context next?",
}


def main():
    parser = argparse.ArgumentParser(description="Generate YouTube upload metadata.")
    parser.add_argument("--script", default="output/script.json", help="Path to script.json")
    parser.add_argument("--output", default="output/metadata.json", help="Output metadata JSON")
    parser.add_argument("--dry-run", action="store_true", help="Use dry-run fixture")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        result = _DRY_RUN_METADATA
    else:
        script_path = Path(args.script)
        if script_path.exists():
            with open(script_path, encoding="utf-8") as f:
                script_data = json.load(f)
        else:
            raise FileNotFoundError(f"Script file not found: {script_path}")

        result = generate_metadata(script_data)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    logger.info(f"Metadata saved -> {output_path}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
