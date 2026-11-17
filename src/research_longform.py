"""Automatically discover a BTS topic and assemble source-attributed evidence."""

import html
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

import requests

from src.fetch_content import BTS_NEWS_FEEDS, HTTP_HEADERS
from src.generate_script import GROQ_API_URL, GROQ_MODEL_FALLBACKS, DEFAULT_GROQ_MODEL

logger = logging.getLogger("research_longform")
MAX_ARTICLES = 30

RESEARCH_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "bts_longform_research_selection",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "selected_source_indices": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
            },
            "required": ["topic", "selected_source_indices"],
            "additionalProperties": False,
        },
    },
}


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        cleaned = re.sub(r"\s+", " ", html.unescape(data)).strip()
        if cleaned:
            self.parts.append(cleaned)


def _clean_excerpt(raw: str) -> str:
    parser = _TextOnly()
    parser.feed(raw or "")
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()[:1800]


def _collect_articles() -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    now = datetime.now(timezone.utc)
    found = {}
    for publisher, feed_url in BTS_NEWS_FEEDS:
        try:
            response = requests.get(feed_url, headers=HTTP_HEADERS, timeout=20)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for item in root.findall(".//item"):
                title = _clean_excerpt(item.findtext("title", ""))
                url = (item.findtext("link") or "").strip()
                raw_description = item.findtext("description") or ""
                content = next(
                    (child.text for child in item if child.tag.rsplit("}", 1)[-1].lower() == "encoded" and child.text),
                    "",
                )
                excerpt = _clean_excerpt(content or raw_description)
                pub_date = item.findtext("pubDate") or ""
                if not title or not url.startswith("https://") or not pub_date.strip():
                    continue
                if not re.search(r"\b(BTS|Bangtan|Jungkook|Jimin|Jin|Suga|Yoongi|RM|Namjoon|J[ -]?Hope|Hobi|V|Taehyung)\b", title, re.I):
                    continue
                try:
                    published = parsedate_to_datetime(pub_date).astimezone(timezone.utc)
                except (TypeError, ValueError, OverflowError):
                    continue
                if published < cutoff or published > now + timedelta(hours=6):
                    continue
                if len(excerpt) < 60:
                    continue
                record = {
                    "publisher": publisher,
                    "title": title,
                    "url": url,
                    "published_at": published.isoformat(),
                    "excerpt": excerpt,
                }
                # A story can appear in several tag feeds. Keep its first source.
                found.setdefault(url, record)
        except Exception as error:
            logger.warning("Unable to read research feed %s: %s", feed_url, error)

    articles = sorted(found.values(), key=lambda article: article["published_at"], reverse=True)
    if len(articles) < 3:
        raise RuntimeError(
            f"Automatic research found only {len(articles)} usable BTS articles in the last 90 days; "
            "at least three distinct source URLs are required."
        )
    return articles[:MAX_ARTICLES]


def obtain_longform_research(output_path) -> tuple[str, str, str]:
    """Find a source-supported topic and return topic, evidence notes, and URLs."""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY environment variable is not set.")

    articles = _collect_articles()
    candidate_text = "\n\n".join(
        f"[{index}] Publisher: {article['publisher']}\n"
        f"Headline: {article['title']}\n"
        f"Date: {article['published_at']}\n"
        f"RSS excerpt: {article['excerpt']}"
        for index, article in enumerate(articles, start=1)
    )
    system_prompt = (
        "Choose one compelling, evergreen-friendly long-form BTS fan commentary topic supported by a coherent set "
        "of at least three supplied news items. Return the exact candidate indices that support the topic. "
        "Use public, reported facts only; do not use rumors, private-life claims, relationship speculation, "
        "or invented facts. Prefer distinct publishers and corroborating context. The topic should explore why "
        "the documented public work or moment resonates with adult women fans, not merely retell headlines. "
        "Select 3 to 6 source indices. Do not invent sources or claims."
    )
    preferred = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
    last_error = None
    selection = None
    for model in dict.fromkeys([preferred, *GROQ_MODEL_FALLBACKS]):
        try:
            response = requests.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "Choose the topic and matching sources from these current RSS records:\n\n" + candidate_text},
                    ],
                    "temperature": 0.2,
                    "max_completion_tokens": 1200,
                    "reasoning_effort": "low",
                    "response_format": RESEARCH_SCHEMA,
                    "include_reasoning": False,
                },
                timeout=120,
            )
            response.raise_for_status()
            selection = json.loads(response.json()["choices"][0]["message"]["content"])
            break
        except Exception as error:
            last_error = error
            logger.warning("Research topic selection failed with %s: %s", model, error)
    if selection is None:
        raise RuntimeError(f"Automatic topic selection failed: {last_error}")

    indices = selection.get("selected_source_indices", [])
    if len(set(indices)) < 3 or any(not isinstance(index, int) or index < 1 or index > len(articles) for index in indices):
        raise ValueError("Automatic research did not select at least three valid, distinct source articles.")
    selected = [articles[index - 1] for index in dict.fromkeys(indices)]
    topic = selection.get("topic", "").strip()
    if not topic:
        raise ValueError("Automatic research did not provide an episode topic.")

    # The evidence pack is assembled directly from publisher RSS records so
    # the model cannot fabricate or paraphrase the underlying reported facts.
    notes = "\n\n".join(
        f"[{index}] {article['publisher']} ({article['published_at']}), headline: {article['title']}\n"
        f"Publisher RSS excerpt: {article['excerpt']}"
        for index, article in enumerate(selected, start=1)
    )
    urls = "\n".join(article["url"] for article in selected)
    if len(notes) < 500:
        raise ValueError("Automatically collected source excerpts are too short to support a long-form script.")

    research_bundle = {
        "topic": topic,
        "research_notes": notes,
        "sources": selected,
        "selection_model": preferred,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "note": "Evidence consists of publisher RSS excerpts; verify source pages during artifact review.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(research_bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Automatic research selected %s sources for topic: %s", len(selected), topic)
    return topic, notes, urls
