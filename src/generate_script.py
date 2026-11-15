"""
generate_script.py — MoneyPrinterTurbo-style Viral Script Generator

Uses the Groq API to generate short-form narration scripts (45–65 words).
Optimized for BTS (Bangtan Sonyeondan) spotlight, records, member milestones & ARMY moments.

Key features (MoneyPrinterTurbo Architecture):
  1. 3-Second Psychological Hook (visual & verbal pattern interrupt)
  2. Micro-cliffhangers and punchy pacing
  3. High-converting subscriber CTA ("Subscribe for daily BTS updates! 💜")
  4. Sentence-by-sentence visual keyword extraction for video clip alignment
  5. Strict BTS Guardrail: Rejects any non-BTS content to keep channel 100% focused.

Usage:
    python src/generate_script.py --niche bts
    python src/generate_script.py --niche bts --dry-run

Groq uses its OpenAI-compatible chat completions endpoint and the existing requests dependency.
"""

import argparse
import json
import logging
import os
import random
import re
import requests
import sys
from pathlib import Path
from typing import Optional

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
            retry=retry_if_exception_type(Exception),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=15),
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
logger = logging.getLogger("generate_script")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_MODEL_FALLBACKS = ["openai/gpt-oss-120b"]

# ── BTS Relevance Guardrail Keywords ──────────────────────────────────────────
BTS_KEYWORDS = [
    "bts", "bangtan", "army", "namjoon", "rm", "seokjin", "jin",
    "yoongi", "suga", "agust d", "hoseok", "j-hope", "jhope",
    "jimin", "taehyung", "v", "jungkook", "jk", "bighit", "hybe",
    "borahae", "love yourself", "map of the soul", "proof"
]

BTS_SYSTEM_PROMPT = """You are a viral YouTube Shorts scriptwriter for a top-tier BTS (Bangtan Sonyeondan) & ARMY channel.

Your goal is to write a high-retention 15–30 second YouTube Short script EXCLUSIVELY about BTS or its members: RM (Kim Namjoon), Jin (Kim Seokjin), SUGA (Min Yoongi / Agust D), J-Hope (Jung Hoseok), Jimin (Park Jimin), V (Kim Taehyung), or Jungkook (Jeon Jungkook).

CRITICAL GUARDRAIL:
You MUST ONLY write about BTS. NEVER generate content about any other unrelated topic. Every script must be 100% focused on BTS milestones, records, member moments, or ARMY history.

HARD RULES:
1. Total narration word count: 45–65 words ONLY.
2. Open on the specific surprising detail or unresolved question in the supplied story. No greeting, channel intro, or generic "Did you know?" opener.
3. Use only the supplied headline and RSS excerpt. Never invent numbers, quotes, dates, motives, records, or member statements. Attribute claims to the named publisher when appropriate.
4. Use a compact story arc: hook, useful context, payoff. End on a specific viewer question that invites a real fan perspective. Do not spend narration time saying "subscribe".
5. Provide 2-3 original graphic ideas for every sentence. Do not request BTS photos, logos, concert clips, music videos, or other copyrighted media.

Output MUST be in raw JSON (no markdown fences):
{
  "hook_text": "<specific 3-5 word hook, no unsupported claim>",
  "title": "<clear, accurate title under 60 characters>",
  "viewer_question": "<specific, answerable question tied to this story>",
  "narration": "<complete narration text>",
  "sentences": [
    {
      "text": "<sentence 1 text>",
      "keywords": ["<keyword1>", "<keyword2>"]
    }
  ],
  "title_keyword": "<main BTS search keyword for video title>"
}
"""

REAL_ESTATE_SYSTEM_PROMPT = """You are a viral YouTube Shorts scriptwriter for a top-tier Real Estate & Luxury Architecture channel.
Your goal is to write a high-retention 15–30 second YouTube Short script about luxury property.
Word count: 45-65 words. Final sentence: "Subscribe for daily luxury real estate tours and secrets!"
Output raw JSON with hook_text, narration, sentences, and title_keyword."""

SPACE_SYSTEM_PROMPT = """You are a viral YouTube Shorts scriptwriter for a science & space channel.
Write a punchy, mind-blowing 15–30 second script about space / astronomy.
Word count: 45-65 words. Final sentence: "Subscribe for daily mind-blowing space facts!"
Output raw JSON with hook_text, narration, sentences, and title_keyword."""


def is_bts_content(script_data: dict) -> bool:
    """Validate that script content is strictly relevant to BTS."""
    text_corpus = (
        script_data.get("narration", "") + " " +
        script_data.get("hook_text", "") + " " +
        script_data.get("title_keyword", "")
    ).lower()

    for kw in BTS_KEYWORDS:
        # Match as whole word or part of token
        if re.search(r"\b" + re.escape(kw) + r"\b", text_corpus):
            return True
    return False


def _get_groq_api_key() -> str:
    """Return the Groq API key from the environment."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY environment variable is not set.")
    return api_key


def _call_groq(system_prompt: str, user_prompt: str) -> str:
    """Call Groq chat completions with a supported JSON-capable model."""
    api_key = _get_groq_api_key()
    preferred_model = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
    models_to_try = list(dict.fromkeys([preferred_model, *GROQ_MODEL_FALLBACKS]))
    last_err = None

    for model_name in models_to_try:
        try:
            logger.info(f"Calling Groq model: {model_name} ...")
            response = requests.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.7,
                    "max_completion_tokens": 1024,
                    "response_format": {"type": "json_object"},
                    "reasoning_format": "hidden",
                },
                timeout=90,
            )
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"].strip()
            if text:
                return text
            raise RuntimeError(f"Groq model '{model_name}' returned an empty response.")
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, RuntimeError) as e:
            logger.warning(f"Groq model '{model_name}' failed: {e}. Trying fallback model...")
            last_err = e

    if last_err:
        raise last_err
    raise RuntimeError("All Groq model attempts failed.")


def _parse_json_response(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Failed to parse Groq response as JSON: {e}")
        return {}


def generate_viral_script(
    niche: str = "bts",
    topic: Optional[str] = None,
    source_content: Optional[dict] = None,
) -> dict:
    """Generate MoneyPrinterTurbo viral script with strict BTS guardrails."""
    if niche == "bts":
        if source_content and source_content.get("title"):
            art_title = source_content.get("title", "BTS News Update")
            art_desc = source_content.get("description", "")
            user_prompt = (
                "Create one source-bound BTS Short from this RSS item. It is one publisher's report, not independently verified. "
                "The RSS excerpt may be incomplete. State only details directly supported by it, attribute the report, and do not fill gaps from memory. "
                "Make the first line instantly specific, build curiosity without misleading, and deliver a satisfying answer before the final viewer question. "
                f"Publisher: {source_content.get('source', 'Unknown')}\n"
                f"Published: {source_content.get('published_at', 'date unavailable')}\n"
                f"Headline: {art_title}\nRSS excerpt: {art_desc}\n"
                f"Source URL: {source_content.get('article_url', '')}"
            )
        else:
            raise ValueError("BTS scripts require a current source item; topic-only generation is disabled.")
        system_prompt = BTS_SYSTEM_PROMPT
    elif niche == "real_estate":
        topic_str = topic or "5 Secrets of $100 Million Mega Mansions"
        user_prompt = f"Write a viral YouTube Short script about real estate topic: '{topic_str}'."
        system_prompt = REAL_ESTATE_SYSTEM_PROMPT
    else:
        topic_str = topic or "Mind-blowing Cosmic Discoveries"
        user_prompt = f"Write a viral YouTube Short script about topic: '{topic_str}'."
        system_prompt = SPACE_SYSTEM_PROMPT

    try:
        _get_groq_api_key()
        raw = _call_groq(system_prompt, user_prompt)
        parsed = _parse_json_response(raw)

        if parsed and "narration" in parsed:
            # Enforce BTS relevance guardrail
            if niche == "bts" and not is_bts_content(parsed):
                raise ValueError("Generated script failed the BTS relevance check")

            narration = parsed["narration"].strip()
            words = narration.split()
            if niche == "bts" and not 45 <= len(words) <= 65:
                raise ValueError(f"Generated BTS narration has {len(words)} words; expected 45-65")
            if niche == "bts" and (not parsed.get("title") or len(parsed["title"].strip()) > 60):
                raise ValueError("Generated BTS title is missing or exceeds 60 characters")
            if niche == "bts" and not parsed.get("viewer_question", "").strip():
                raise ValueError("Generated BTS script is missing its story-specific viewer question")
            parsed["word_count"] = len(words)
            parsed["niche"] = niche
            logger.info(f"Generated BTS viral script ({len(words)} words): {narration[:60]}...")
            return parsed

    except Exception as e:
        if niche == "bts":
            raise RuntimeError(f"BTS script generation failed; refusing to publish an unsupported fallback: {e}") from e
        logger.warning(f"Groq API generation unavailable ({e}). Using offline fallback script.")

    return get_fallback_script(niche, topic)


# ── BTS Offline Fallback Templates ─────────────────────────────────────────────
_BTS_FALLBACK_TEMPLATES = [
    {
        "hook_text": "BTS Historic World Record",
        "narration": (
            "Did you know BTS holds over thirty Guinness World Records? "
            "They became the first group in history to hold multiple Billboard number-one debuts. "
            "Their global impact inspired millions and brought Korean music to the United Nations. "
            "Subscribe for daily BTS updates and ARMY facts! 💜"
        ),
        "sentences": [
            {
                "text": "Did you know BTS holds over thirty Guinness World Records?",
                "keywords": ["stadium concert crowd", "purple neon stage"]
            },
            {
                "text": "They became the first group in history to hold multiple Billboard number-one debuts.",
                "keywords": ["music award trophy", "kpop stage performance"]
            },
            {
                "text": "Their global impact inspired millions and brought Korean music to the United Nations.",
                "keywords": ["united nations assembly", "purple ocean concert"]
            },
            {
                "text": "Subscribe for daily BTS updates and ARMY facts! 💜",
                "keywords": ["purple lights crowd", "kpop concert stadium"]
            }
        ],
        "title_keyword": "BTS World Records",
        "word_count": 52,
        "niche": "bts",
        "fallback": True,
    },
    {
        "hook_text": "Jungkook Golden Record",
        "narration": (
            "Jungkook made music history by smashing one billion streams faster than any soloist. "
            "His debut album Golden dominated global charts in over one hundred countries. "
            "From the youngest member to a worldwide superstar, his journey is legendary. "
            "Subscribe for daily BTS updates and ARMY facts! 💜"
        ),
        "sentences": [
            {
                "text": "Jungkook made music history by smashing one billion streams faster than any soloist.",
                "keywords": ["music streaming record", "concert microphone stage"]
            },
            {
                "text": "His debut album Golden dominated global charts in over one hundred countries.",
                "keywords": ["gold vinyl record", "billboard music charts"]
            },
            {
                "text": "From the youngest member to a worldwide superstar, his journey is legendary.",
                "keywords": ["stadium concert performance", "purple lights stage"]
            },
            {
                "text": "Subscribe for daily BTS updates and ARMY facts! 💜",
                "keywords": ["purple ocean army", "kpop stadium crowd"]
            }
        ],
        "title_keyword": "Jungkook Records",
        "word_count": 52,
        "niche": "bts",
        "fallback": True,
    },
    {
        "hook_text": "Jin Secret Promise",
        "narration": (
            "Jin touched millions of fans with a heartfelt promise made right before military service. "
            "The moment he finished duty, he immediately held a warm hug event for ARMY. "
            "His unwavering loyalty proves why BTS and ARMY have an unbreakable bond. "
            "Subscribe for daily BTS updates and ARMY facts! 💜"
        ),
        "sentences": [
            {
                "text": "Jin touched millions of fans with a heartfelt promise made right before military service.",
                "keywords": ["heartwarming fan moment", "purple aesthetic stage"]
            },
            {
                "text": "The moment he finished duty, he immediately held a warm hug event for ARMY.",
                "keywords": ["fan meeting stadium", "kpop idol smile"]
            },
            {
                "text": "His unwavering loyalty proves why BTS and ARMY have an unbreakable bond.",
                "keywords": ["purple ocean concert", "stadium lightsticks"]
            },
            {
                "text": "Subscribe for daily BTS updates and ARMY facts! 💜",
                "keywords": ["purple lights crowd", "bts concert celebration"]
            }
        ],
        "title_keyword": "BTS Jin Promise",
        "word_count": 53,
        "niche": "bts",
        "fallback": True,
    }
]


def get_fallback_script(niche: str = "bts", topic: Optional[str] = None) -> dict:
    """Offline high-converting script template when AI API is unconfigured/offline."""
    if niche == "bts":
        raise RuntimeError("There is no safe generic BTS fallback. Provide a recent source item.")
    elif niche == "real_estate":
        return {
            "hook_text": "Inside $100M Mega Mansion",
            "narration": (
                "Inside this $100 Million Mega Mansion lies a secret room hidden behind a waterfall. "
                "The primary suite spans 3,000 square feet with 24-karat gold finishes. "
                "An underground garage houses up to twenty supercar collectibles. "
                "Subscribe for daily luxury real estate tours and secrets!"
            ),
            "sentences": [
                {
                    "text": "Inside this $100 Million Mega Mansion lies a secret room hidden behind a waterfall.",
                    "keywords": ["luxury mansion pool", "modern villa exterior"]
                },
                {
                    "text": "The primary suite spans 3,000 square feet with 24-karat gold finishes.",
                    "keywords": ["luxury penthouse bedroom", "modern interior design"]
                },
                {
                    "text": "An underground garage houses up to twenty supercar collectibles.",
                    "keywords": ["luxury garage supercar", "modern architecture"]
                },
                {
                    "text": "Subscribe for daily luxury real estate tours and secrets!",
                    "keywords": ["luxury home living room", "modern house tour"]
                }
            ],
            "title_keyword": "Mega Mansion Secrets",
            "word_count": 52,
            "niche": "real_estate",
            "fallback": True,
        }
    else:
        return {
            "hook_text": "Close Stellar Nursery",
            "narration": (
                "Inside this glowing cosmic cloud, thousands of new stars are being born right now. "
                "The Orion Nebula is located 1,344 light-years away from Earth. "
                "Hubble captured incredible forming solar systems inside these gas pillars. "
                "Subscribe for daily mind-blowing space facts!"
            ),
            "sentences": [
                {
                    "text": "Inside this glowing cosmic cloud, thousands of new stars are being born right now.",
                    "keywords": ["space nebula stars", "galaxy cosmic cloud"]
                },
                {
                    "text": "The Orion Nebula is located 1,344 light-years away from Earth.",
                    "keywords": ["orion nebula deep space", "planet earth space"]
                },
                {
                    "text": "Hubble captured incredible forming solar systems inside these gas pillars.",
                    "keywords": ["hubble telescope space", "solar system forming"]
                },
                {
                    "text": "Subscribe for daily mind-blowing space facts!",
                    "keywords": ["deep space universe", "stars galaxy animation"]
                }
            ],
            "title_keyword": "Orion Nebula",
            "word_count": 51,
            "niche": "space",
            "fallback": True,
        }


# ── DRY RUN ────────────────────────────────────────────────────────────────────
_DRY_RUN_SCRIPT = _BTS_FALLBACK_TEMPLATES[0].copy()
_DRY_RUN_SCRIPT["dry_run"] = True


def main():
    parser = argparse.ArgumentParser(description="Generate MoneyPrinterTurbo viral script.")
    parser.add_argument("--niche", default="bts", help="Niche: bts | real_estate | space")
    parser.add_argument("--topic", default=None, help="Custom topic prompt")
    parser.add_argument("--output", default="output/script.json", help="Output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Use dry-run fixture")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        result = _DRY_RUN_SCRIPT
    else:
        result = generate_viral_script(niche=args.niche, topic=args.topic)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    logger.info(f"Script saved -> {output_path}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
