"""Generate source-bounded, original long-form BTS fan commentary."""

import json
import logging
import os
import re
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
- Make five distinct chapters totaling 1,150–1,450 spoken words. Chapters should each be about 200–300 words. Write natural voiceover prose, not bullets or stage directions.
- For every chapter, list the one-based indices of the research source URLs that support its factual claims. Do not make up source indices.
- Give an accurate, appealing title (under 90 characters) and thumbnail text of 2–5 words. Avoid misleading promises or clickbait.

The supplied notes are evidence, not text to copy. Return only the required JSON."""
    source_list = "\n".join(f"[{index}] {url}" for index, url in enumerate(sources, start=1))
    user_prompt = (
        f"EPISODE TOPIC: {topic.strip()}\n\n"
        f"RESEARCH NOTES (facts should be traceable to the numbered links):\n{research_notes.strip()}\n\n"
        f"SOURCE URLS:\n{source_list}\n\n"
        "Audience promise: a warm, witty, emotionally intelligent fan perspective on why BTS members' public creative work and public moments resonate with women fans. "
        "Keep the discussion centered on admiration and fandom; do not imply romantic access to the members."
    )

    preferred_model = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
    models = list(dict.fromkeys([preferred_model, *GROQ_MODEL_FALLBACKS]))
    last_error = None
    parsed = None
    for model in models:
        try:
            response = requests.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.55,
                    "max_completion_tokens": 6000,
                    "reasoning_effort": "low",
                    "response_format": LONGFORM_SCHEMA,
                    "include_reasoning": False,
                },
                timeout=180,
            )
            response.raise_for_status()
            body = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(body)
            break
        except Exception as error:
            last_error = error
            logger.warning("Long-form generation failed with %s: %s", model, error)
    if parsed is None:
        raise RuntimeError(f"All long-form script generation attempts failed: {last_error}")

    chapters = parsed.get("chapters", [])
    if len(chapters) != 5:
        raise ValueError(f"Expected 5 distinct chapters; model returned {len(chapters)}.")
    total_words = 0
    for chapter in chapters:
        text = chapter.get("narration", "").strip()
        if not text or not chapter.get("title"):
            raise ValueError("Every long-form chapter needs a title and narration.")
        total_words += len(text.split())
        indices = chapter.get("source_indices", [])
        if not indices or any(index < 1 or index > len(sources) for index in indices):
            raise ValueError("Every chapter must cite valid source indices from the supplied source list.")
    if not 1150 <= total_words <= 1450:
        raise ValueError(f"Generated narration has {total_words} words; expected 1,150–1,450.")

    parsed["chapters"] = chapters
    parsed["source_urls"] = sources
    parsed["narration"] = "\n\n".join(chapter["narration"].strip() for chapter in chapters)
    parsed["word_count"] = total_words
    parsed["niche"] = "bts_longform"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Generated long-form script: %s words, %s chapters", total_words, len(chapters))
    return parsed
