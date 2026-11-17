"""Generate source-bounded, original long-form BTS fan commentary."""

import json
import logging
import os
import re
import time
from pathlib import Path

import requests

from src.generate_script import GROQ_API_URL, GROQ_MODEL_FALLBACKS, DEFAULT_GROQ_MODEL

logger = logging.getLogger("generate_longform")

LONGFORM_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "bts_longform_fan_commentary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "thumbnail_text": {"type": "string"},
                "viewer_question": {"type": "string"},
                "chapters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "narration": {"type": "string"},
                            "source_indices": {"type": "array", "items": {"type": "integer"}},
                        },
                        "required": ["title", "narration", "source_indices"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["title", "thumbnail_text", "viewer_question", "chapters"],
            "additionalProperties": False,
        },
    },
}


def _parse_sources(source_text: str) -> list[str]:
    urls = []
    for raw in re.split(r"[\r\n,]+", source_text):
        url = raw.strip()
        if url and url not in urls:
            if not url.startswith("https://"):
                raise ValueError(f"Source links must use HTTPS: {url}")
            urls.append(url)
    if len(urls) < 3:
        raise ValueError("Provide at least three source URLs (prefer official BTS/BIGHIT sources and reputable reporting).")
    return urls


def _validate_generated_script(parsed: dict, source_count: int) -> tuple[list[dict], int, list[str]]:
    chapters = parsed.get("chapters", [])
    errors = []
    if len(chapters) != 5:
        errors.append(f"return exactly five chapters (received {len(chapters)})")

    total_words = 0
    for chapter_number, chapter in enumerate(chapters, start=1):
        narration = chapter.get("narration", "").strip()
        if not narration or not chapter.get("title"):
            errors.append(f"chapter {chapter_number} needs a title and narration")
        chapter_words = len(narration.split())
        total_words += chapter_words
        if narration and not 150 <= chapter_words <= 350:
            errors.append(f"chapter {chapter_number} has {chapter_words} words; expected 150-350 words")

        indices = chapter.get("source_indices", [])
        if not isinstance(indices, list) or not indices:
            errors.append(f"chapter {chapter_number} needs source_indices")
            continue
        if any(not isinstance(index, int) or isinstance(index, bool) for index in indices):
            errors.append(f"chapter {chapter_number} has non-integer source_indices {indices!r}")
            continue

        # Some models ignore the one-based instruction and return 0-based
        # indices. Convert that chapter only when zero makes the convention clear.
        if 0 in indices and all(0 <= index < source_count for index in indices):
            indices = [index + 1 for index in indices]
            chapter["source_indices"] = indices
        if any(index < 1 or index > source_count for index in indices):
            errors.append(
                f"chapter {chapter_number} cites {indices!r}; allowed source indices are 1 through {source_count}"
            )

    if not 900 <= total_words <= 1800:
        errors.append(f"narration must contain 900-1,800 words (received {total_words})")
    return chapters, total_words, errors


def generate_longform_script(topic: str, research_notes: str, source_text: str, output_path: Path) -> dict:
    if len(research_notes.strip()) < 500:
        raise ValueError("Provide at least 500 characters of fact-checked research notes before generating a long-form script.")
    sources = _parse_sources(source_text)
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY environment variable is not set.")

    system_prompt = """You are the original commentator and writer for a thoughtful BTS fan channel for adult women and ARMY. Write a complete, engaging 8–10 minute YouTube video about BTS fans' admiration and crushes, grounded in the supplied research notes.

Editorial rules:
- Treat attraction as a fan's subjective response to public artistry, stage presence, humor, teamwork, or public comments. Never claim to know a member's private personality, feelings, dating life, or relationship with a viewer.
- Keep the language respectful and suitable for a general audience. Do not sexualize anyone, encourage parasocial delusions, or target minors.
- Use only factual details stated in the research notes. Clearly distinguish fact, attributed reporting, and your own fan interpretation. Never invent quotes, dates, numbers, or anecdotes.
- Write substantial original analysis, not an article reading, biography dump, ranking, compilation script, or repeated template. Do not reproduce song lyrics or long quotes.
- Start with a compelling cold open that immediately promises the specific payoff. Deliver a new idea in every chapter, use natural transitions, and finish with a brief subscribe invitation followed by the viewer question.
- Aim for five distinct chapters totaling 1,200–1,400 spoken words, with roughly 200–280 words per chapter. Keep every chapter meaningful and source-grounded. A complete script may be shorter when the supplied evidence is limited; never pad it with repetition. Write natural voiceover prose, not bullets or stage directions.
- For every chapter, list the one-based indices of the research source URLs that support its factual claims. Do not make up source indices.
- Give an accurate, appealing title (under 90 characters) and thumbnail text of 2–5 words. Avoid misleading promises or clickbait.

The supplied notes are evidence, not text to copy. Return only the required JSON."""
    source_list = "\n".join(f"[{index}] {url}" for index, url in enumerate(sources, start=1))
    user_prompt = (
        f"EPISODE TOPIC: {topic.strip()}\n\n"
        f"RESEARCH NOTES (facts should be traceable to the numbered links):\n{research_notes.strip()}\n\n"
        f"SOURCE URLS:\n{source_list}\n\n"
        f"VALID CITATION INDICES: {', '.join(str(index) for index in range(1, len(sources) + 1))}. "
        "Use only these exact one-based numbers in every chapter's source_indices array.\n\n"
        "Audience promise: a warm, witty, emotionally intelligent fan perspective on why BTS members' public creative work and public moments resonate with women fans. "
        "Keep the discussion centered on admiration and fandom; do not imply romantic access to the members."
    )

    preferred_model = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
    models = list(dict.fromkeys([preferred_model, *GROQ_MODEL_FALLBACKS]))
    last_error = None
    parsed = None
    for model in models:
        correction = ""
        rate_limit_retries = 0
        attempt = 0
        while attempt < 4:
            try:
                response = requests.post(
                    GROQ_API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt + correction},
                        ],
                        "temperature": 0.4 if attempt else 0.55,
                        "max_completion_tokens": 8000,
                        "reasoning_effort": "low",
                        "response_format": LONGFORM_SCHEMA,
                        "include_reasoning": False,
                    },
                    timeout=180,
                )
                response.raise_for_status()
                body = response.json()["choices"][0]["message"]["content"]
                candidate = json.loads(body)
                chapters, total_words, validation_errors = _validate_generated_script(candidate, len(sources))
                if validation_errors:
                    last_error = "; ".join(validation_errors)
                    logger.warning("Long-form output from %s needs correction: %s", model, last_error)
                    correction = (
                        "\n\nCORRECTION REQUIRED: Your previous output failed validation: " + last_error + ". "
                        f"Use only one-based source indices 1 through {len(sources)} (the available URLs are numbered 1 to {len(sources)}). "
                        "Every chapter must cite at least one valid source. Return a corrected complete JSON object. "
                        "Expand short chapters only with useful source-grounded explanation and original fan analysis; do not add filler. "
                        "Keep each chapter between 150 and 350 words and the complete narration between 900 and 1,800 words."
                    )
                    attempt += 1
                    continue
                candidate["chapters"] = chapters
                candidate["word_count"] = total_words
                parsed = candidate
                break
            except Exception as error:
                last_error = error
                response = getattr(error, "response", None)
                detail = getattr(response, "text", "")[:1000] if response is not None else ""
                logger.warning("Long-form generation failed with %s: %s %s", model, error, detail)
                status = getattr(response, "status_code", None)
                if status == 429 and rate_limit_retries < 2:
                    retry_after = getattr(error.response, "headers", {}).get("Retry-After")
                    try:
                        delay = min(120, max(1, int(float(retry_after))))
                    except (TypeError, ValueError):
                        delay = 30 * (2 ** rate_limit_retries)
                    rate_limit_retries += 1
                    logger.warning("Groq rate limit reached; retrying %s after %s seconds.", model, delay)
                    time.sleep(delay)
                    continue
                if status == 429:
                    logger.warning("Groq rate limit retry limit reached for %s; moving to fallback model.", model)
                break
        if parsed is not None:
            break
    if parsed is None:
        raise RuntimeError(f"Long-form generation could not produce a valid script after retries: {last_error}")

    chapters = parsed.get("chapters", [])
    total_words = parsed["word_count"]

    parsed["chapters"] = chapters
    parsed["source_urls"] = sources
    parsed["narration"] = "\n\n".join(chapter["narration"].strip() for chapter in chapters)
    parsed["word_count"] = total_words
    parsed["niche"] = "bts_longform"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Generated long-form script: %s words, %s chapters", total_words, len(chapters))
    return parsed
