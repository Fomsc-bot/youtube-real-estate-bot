"""
generate_script.py — MoneyPrinterTurbo-style Viral Script Generator

Uses Google Gemini AI to turn real estate or space topics into viral short-form
narration scripts (45–70 words).

Key features (MoneyPrinterTurbo Architecture):
  1. 3-Second Psychological Hook (visual & verbal pattern interrupt)
  2. Micro-cliffhangers and punchy pacing
  3. High-converting subscriber CTA ("Subscribe for daily luxury tours!")
  4. Sentence-by-sentence visual keyword extraction for Pexels stock video alignment

Usage:
    python src/generate_script.py --niche real_estate
    python src/generate_script.py --niche space --dry-run
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

try:
    import google.generativeai as genai
except ImportError:
    genai = None

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

# ── System Prompts ─────────────────────────────────────────────────────────────
REAL_ESTATE_SYSTEM_PROMPT = """You are a viral YouTube Shorts scriptwriter for a top-tier Real Estate & Luxury Architecture channel.

Your goal is to write a high-retention 15–30 second YouTube Short script about real estate / luxury property / architectural marvels / home buying secrets.

HARD RULES:
1. Total word count: 45–68 words ONLY.
2. Sentence 1 MUST be an irresistible viral hook (pattern interrupt / curiosity gap). Example: "Do NOT buy a mansion until you check this legal loophole..." or "Inside this $120 Million Mega Mansion lies a secret room..."
3. Short, high-energy sentences (max 10-12 words per sentence).
4. Final sentence MUST be a high-conversion subscriber CTA: "Subscribe for daily luxury real estate tours and secrets!"
5. For EVERY sentence in the narration, provide 2-3 visual search keywords suitable for Pexels HD stock video search (e.g., ["luxury mansion pool", "modern villa exterior"]).

Output MUST be in raw JSON (no markdown fences):
{
  "hook_text": "<3-5 word intriguing video overlay title>",
  "narration": "<complete narration text>",
  "sentences": [
    {
      "text": "<sentence 1 text>",
      "keywords": ["<keyword1>", "<keyword2>"]
    }
  ],
  "title_keyword": "<main search keyword for video title>"
}
"""

SPACE_SYSTEM_PROMPT = """You are a viral YouTube Shorts scriptwriter for a science & space channel.

Write a punchy, mind-blowing 15–30 second script about space / astronomy.

HARD RULES:
1. Total word count: 45–68 words ONLY.
2. Sentence 1 MUST be a viral hook stating the most surprising space fact immediately.
3. Short, punchy sentences.
4. Final sentence MUST be: "Subscribe for daily mind-blowing space facts!"
5. Provide visual search keywords for Pexels HD video search for each sentence.

Output MUST be in raw JSON (no markdown fences):
{
  "hook_text": "<3-5 word intriguing overlay title>",
  "narration": "<complete narration text>",
  "sentences": [
    {
      "text": "<sentence 1 text>",
      "keywords": ["<keyword1>", "<keyword2>"]
    }
  ],
  "title_keyword": "<main keyword>"
}
"""


def _init_gemini() -> None:
    if genai is None:
        raise EnvironmentError("google-generativeai module not installed.")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is not set.")
    genai.configure(api_key=api_key)


def _call_gemini(system_prompt: str, user_prompt: str) -> str:
    """Call Gemini with multi-model automatic failover."""
    models_to_try = ["gemini-2.0-flash-lite", "gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
    last_err = None

    for model_name in models_to_try:
        try:
            logger.info(f"Calling Gemini model: {model_name} ...")
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_prompt,
            )
            response = model.generate_content(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=512,
                    response_mime_type="application/json",
                ),
                request_options={"timeout": 30},
            )
            text = response.text.strip()
            if text:
                return text
        except Exception as e:
            logger.warning(f"Gemini model '{model_name}' failed: {e}. Trying fallback model...")
            last_err = e

    if last_err:
        raise last_err
    raise RuntimeError("All Gemini model attempts failed.")


def _parse_json_response(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Failed to parse Gemini response as JSON: {e}")
        return {}


def generate_viral_script(
    niche: str = "real_estate",
    topic: Optional[str] = None,
    source_content: Optional[dict] = None,
) -> dict:
    """Generate MoneyPrinterTurbo viral script for real_estate or space."""
    if niche == "space" and source_content:
        title = source_content.get("title", "Space Discovery")
        explanation = source_content.get("explanation", "")
        user_prompt = f"Topic: {title}\nExplanation: {explanation[:1500]}\nGenerate viral script with keywords."
        system_prompt = SPACE_SYSTEM_PROMPT
    elif niche == "real_estate":
        topic_str = topic or "5 Secrets of $100 Million Mega Mansions"
        user_prompt = f"Write a viral YouTube Short script about real estate topic: '{topic_str}'."
        system_prompt = REAL_ESTATE_SYSTEM_PROMPT
    else:
        topic_str = topic or "Mind-blowing Cosmic Discoveries"
        user_prompt = f"Write a viral YouTube Short script about topic: '{topic_str}'."
        system_prompt = SPACE_SYSTEM_PROMPT

    try:
        _init_gemini()
        raw = _call_gemini(system_prompt, user_prompt)
        parsed = _parse_json_response(raw)

        if parsed and "narration" in parsed:
            narration = parsed["narration"].strip()
            words = narration.split()
            parsed["word_count"] = len(words)
            parsed["niche"] = niche
            logger.info(f"Generated viral script ({len(words)} words): {narration[:60]}...")
            return parsed

    except Exception as e:
        logger.warning(f"Gemini API generation unavailable ({e}). Using offline viral script generator.")

    return get_fallback_script(niche, topic)


def get_fallback_script(niche: str = "real_estate", topic: Optional[str] = None) -> dict:
    """Offline high-converting script template when AI API is unconfigured/offline."""
    if niche == "real_estate":
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
_DRY_RUN_SCRIPT = {
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
    "dry_run": True,
}


def main():
    parser = argparse.ArgumentParser(description="Generate MoneyPrinterTurbo viral script.")
    parser.add_argument("--niche", default="real_estate", help="Niche: real_estate | space")
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
