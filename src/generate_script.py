"""
generate_script.py — Step 2 of The Universe pipeline.

Uses Google Gemini API to turn NASA APOD explanation text into a punchy
15–25 second narration script (50–72 words) optimised for TTS pacing
and YouTube Shorts virality.

Usage:
    python src/generate_script.py --apod output/apod.json
    python src/generate_script.py --apod output/apod.json --dry-run
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import google.generativeai as genai
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
logger = logging.getLogger("generate_script")

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a science short-form content writer for the YouTube Shorts channel 'The Universe'.

Your job is to turn a NASA Astronomy Picture of the Day (APOD) explanation into a narration script for a 15–25 second YouTube Short.

HARD RULES:
1. Total word count: 50–72 words ONLY. Count carefully.
2. First sentence must be a hook — state the most surprising fact immediately. No "hello", no "today we're looking at", no throat-clearing.
3. Use only facts that are explicitly present in the provided APOD explanation. Do NOT invent or extrapolate figures.
4. Short punchy sentences. Maximum 12 words per sentence. Suited for TTS pacing.
5. Final sentence must be exactly: "Follow for daily space facts."
6. No clickbait that isn't paid off by the script. No exaggeration.
7. Write for spoken audio — avoid punctuation that sounds wrong aloud (em dashes, semicolons). Commas and periods only.
8. Do NOT include stage directions, speaker labels, or formatting — plain narration text only.

Also output (separately, not in the narration):
- HOOK_TEXT: A 3–5 word bold title for the video overlay (first 2 seconds). Make it intriguing. Example: "Star Factory Revealed" or "1,000 Light-Years Away"
- TITLE_KEYWORD: The single most searchable keyword from this content (e.g. "Orion Nebula", "Black Hole", "Saturn")
"""

USER_PROMPT_TEMPLATE = """APOD Title: {title}

APOD Explanation (source text — use ONLY facts from this):
{explanation}

Now write the narration script and the HOOK_TEXT and TITLE_KEYWORD.

Respond in this exact JSON format (no markdown fences):
{{
  "narration": "<50-72 word script ending with 'Follow for daily space facts.'>",
  "hook_text": "<3-5 word overlay title>",
  "title_keyword": "<single most searchable keyword>"
}}"""

NEO_SYSTEM_PROMPT = """You are a science short-form content writer for the YouTube Shorts channel 'The Universe'.

Write a narration script for an 'Asteroid Watch' weekly Short (15–25 seconds).

HARD RULES:
1. Total word count: 50–72 words ONLY.
2. Open with the most alarming but honest fact about the closest asteroid this week.
3. Use ONLY the data provided — no invention.
4. Short punchy sentences, max 12 words each.
5. Final sentence must be exactly: "Follow for daily space facts."
6. No exaggeration. Hazardous does NOT mean it will hit Earth — say it correctly.
7. Plain narration text only.
"""

NEO_USER_PROMPT_TEMPLATE = """Asteroid Watch data for this week:
- Total near-Earth objects: {count}
- Closest approach: {name}, passing {miss_km:,} km away on {date}
- Estimated diameter: {diameter} km
- Potentially hazardous: {hazardous}
- Total hazardous objects this week: {hazardous_count}

Respond in this exact JSON format (no markdown fences):
{{
  "narration": "<50-72 word script ending with 'Follow for daily space facts.'>",
  "hook_text": "<3-5 word overlay title, e.g. 'Asteroid Close Call'>",
  "title_keyword": "Asteroid Watch"
}}"""


# ── Retry decorator ────────────────────────────────────────────────────────────
def _make_retry():
    return retry(
        retry=retry_if_exception_type(Exception),   # MUST be keyword arg
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=3, max=45),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


def _init_gemini() -> None:
    """Initialise the Gemini SDK with the API key from environment."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY environment variable is not set. "
            "Add it as a GitHub Secret or set it locally."
        )
    genai.configure(api_key=api_key)


@_make_retry()
def _call_gemini(model_name: str, system_prompt: str, user_prompt: str) -> str:
    """Make a Gemini API call and return raw text response."""
    try:
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_prompt,
        )
        logger.info(f"Calling Gemini model: {model_name} ...")
        response = model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=512,
                response_mime_type="application/json",
            ),
            request_options={"timeout": 30},   # 30-second hard timeout
        )
        text = response.text.strip()
        logger.info(f"Gemini response received ({len(text)} chars)")
        return text
    except Exception as e:
        # Check if it's a 429 quota error
        if "429" in str(e) or "404" in str(e):
            logger.warning(f"Hit 429/404 Error on {model_name}. Attempting fallback...")
            fallback_model = "gemini-2.5-flash" if "lite" in model_name else "gemini-2.5-flash-lite"
            logger.info(f"Calling fallback Gemini model: {fallback_model} ...")
            model = genai.GenerativeModel(
                model_name=fallback_model,
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
            logger.info(f"Fallback Gemini response received ({len(text)} chars)")
            return text
        # Reraise if not 429 or fallback also fails
        raise


def _parse_json_response(raw: str) -> dict:
    """Extract JSON from Gemini response — handles markdown fences if present."""
    # Strip markdown fences if Gemini added them despite instructions
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()
    return json.loads(raw)


def _word_count(text: str) -> int:
    return len(text.split())


def generate_apod_script(apod_data: dict, model_name: str = "gemini-2.5-flash-lite") -> dict:
    """
    Generate narration script from APOD metadata using Gemini.
    Returns dict with narration, hook_text, title_keyword, word_count.
    """
    _init_gemini()

    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=apod_data["title"],
        explanation=apod_data["explanation"][:2000],  # Truncate to avoid token waste
    )

    raw = _call_gemini(model_name, SYSTEM_PROMPT, user_prompt)
    parsed = _parse_json_response(raw)

    narration = parsed.get("narration", "").strip()
    wc = _word_count(narration)
    logger.info(f"Generated script: {wc} words — '{narration[:60]}...'")

    if wc < 40 or wc > 80:
        logger.warning(f"Word count {wc} is outside target range 50–72. Proceeding anyway.")

    return {
        "narration": narration,
        "hook_text": parsed.get("hook_text", apod_data["title"][:30]),
        "title_keyword": parsed.get("title_keyword", "Space"),
        "word_count": wc,
        "apod_title": apod_data["title"],
        "apod_date": apod_data.get("date", ""),
        "content_type": "apod",
    }


def generate_neo_script(neo_data: dict, model_name: str = "gemini-2.5-flash-lite") -> dict:
    """Generate narration script from NEO asteroid data using Gemini."""
    _init_gemini()

    top = neo_data.get("top_asteroid", {})
    user_prompt = NEO_USER_PROMPT_TEMPLATE.format(
        count=neo_data.get("count", 0),
        name=top.get("name", "an unknown asteroid"),
        miss_km=int(top.get("miss_distance_km") or 0),
        date=top.get("date", "this week"),
        diameter=top.get("diameter_km", "unknown"),
        hazardous="Yes" if top.get("is_potentially_hazardous") else "No",
        hazardous_count=neo_data.get("hazardous_count", 0),
    )

    raw = _call_gemini(model_name, NEO_SYSTEM_PROMPT, user_prompt)
    parsed = _parse_json_response(raw)

    narration = parsed.get("narration", "").strip()
    wc = _word_count(narration)
    logger.info(f"Generated NEO script: {wc} words")

    return {
        "narration": narration,
        "hook_text": parsed.get("hook_text", "Asteroid Close Call"),
        "title_keyword": "Asteroid Watch",
        "word_count": wc,
        "content_type": "asteroid_watch",
    }


# ── DRY RUN fixture ────────────────────────────────────────────────────────────
_DRY_RUN_SCRIPT = {
    "narration": (
        "Inside this glowing cloud, thousands of new stars are being born right now. "
        "The Orion Nebula is just 1,344 light-years away, making it the closest stellar "
        "nursery to Earth. Hubble revealed entire solar systems forming inside these "
        "gas pillars. We can actually watch stars being created. "
        "Follow for daily space facts."
    ),
    "hook_text": "Stars Being Born Now",
    "title_keyword": "Orion Nebula",
    "word_count": 62,
    "apod_title": "The Orion Nebula in Infrared",
    "apod_date": "2024-07-04",
    "content_type": "apod",
    "dry_run": True,
}


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Generate narration script from APOD/NEO data.")
    parser.add_argument("--apod", default="output/apod.json", help="Path to apod.json")
    parser.add_argument("--neo", default=None, help="Path to neo.json (for asteroid watch)")
    parser.add_argument("--output", default="output/script.json", help="Output path for script JSON")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Gemini model name")
    parser.add_argument("--dry-run", action="store_true", help="Skip Gemini API; write fixture data")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        logger.info("DRY RUN — writing fixture script data.")
        with open(output_path, "w") as f:
            json.dump(_DRY_RUN_SCRIPT, f, indent=2)
        print(json.dumps(_DRY_RUN_SCRIPT, indent=2))
        return

    if args.neo:
        with open(args.neo) as f:
            neo_data = json.load(f)
        result = generate_neo_script(neo_data, model_name=args.model)
    else:
        with open(args.apod) as f:
            apod_data = json.load(f)
        result = generate_apod_script(apod_data, model_name=args.model)

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)
    logger.info(f"Script saved → {output_path}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
