"""
reply_comments.py — Step 7 of The Universe pipeline.

Runs ~3 hours after upload (separate GitHub Actions workflow).
Fetches new comments on the most recently uploaded video,
generates on-brand replies using Gemini, and posts them.

Spam and off-topic comments are skipped automatically.

Usage:
    python src/reply_comments.py --video-id <YT_VIDEO_ID>
    python src/reply_comments.py --video-id <YT_VIDEO_ID> --dry-run
    python src/reply_comments.py --auto   # reads video_id from upload_result.json
"""

import argparse
import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Optional

import google.generativeai as genai
from googleapiclient.errors import HttpError
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
logger = logging.getLogger("reply_comments")

# ── Config ─────────────────────────────────────────────────────────────────────
MIN_COMMENT_LENGTH = 15
MAX_REPLIES_PER_RUN = 10
SPAM_KEYWORDS = [
    "subscribe back", "sub4sub", "check out my", "visit my channel",
    "click here", "free money", "earn $", "http://", "bit.ly",
    "follow me back", "promo", "discount", "giveaway", "dm me",
    "whatsapp", "telegram",
]

REPLY_SYSTEM_PROMPT = """You are the community manager for 'The Universe' YouTube Shorts channel.
Your replies should feel warm, genuine, science-enthusiastic, and short (1–2 sentences max).

Rules:
1. Directly acknowledge what the commenter said.
2. Add one brief space fact or expansion if relevant — but ONLY if it's accurate.
3. Never mention competitors, other channels, or politics.
4. Keep it under 30 words.
5. No emojis spam — max 1 emoji per reply.
6. Do NOT ask for subscribers in the reply.
7. Sound like a knowledgeable friend, not a bot.
8. If the comment is a question you can't answer accurately, just say so honestly.
"""

REPLY_USER_TEMPLATE = """Video topic: {topic}
Commenter said: "{comment}"

Write a warm, science-enthusiastic reply (1–2 sentences, max 30 words)."""


def _init_gemini() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is not set.")
    genai.configure(api_key=api_key)


def _is_spam(comment_text: str) -> bool:
    """Return True if the comment appears to be spam or off-topic."""
    lower = comment_text.lower()
    for kw in SPAM_KEYWORDS:
        if kw in lower:
            logger.info(f"Skipping spam comment (matched '{kw}'): {comment_text[:60]}")
            return True
    if len(comment_text.strip()) < MIN_COMMENT_LENGTH:
        logger.info(f"Skipping too-short comment: '{comment_text[:40]}'")
        return True
    return False


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=3, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _generate_reply(comment_text: str, topic: str, model_name: str = "gemini-1.5-flash") -> str:
    """Use Gemini to generate an on-brand reply."""
    _init_gemini()
    prompt = REPLY_USER_TEMPLATE.format(topic=topic, comment=comment_text[:300])
    try:
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=REPLY_SYSTEM_PROMPT,
        )
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.6,
                max_output_tokens=80,
            ),
            request_options={"timeout": 30},
        )
        reply = response.text.strip()
        logger.info(f"Generated reply: {reply}")
        return reply
    except Exception as e:
        if "429" in str(e):
            logger.warning(f"Hit 429 Quota Error on {model_name}. Attempting fallback...")
            fallback_model = "gemini-1.5-pro" if "flash" in model_name else "gemini-1.5-flash"
            logger.info(f"Calling fallback Gemini model: {fallback_model} ...")
            model = genai.GenerativeModel(
                model_name=fallback_model,
                system_instruction=REPLY_SYSTEM_PROMPT,
            )
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.6,
                    max_output_tokens=80,
                ),
                request_options={"timeout": 30},
            )
            reply = response.text.strip()
            logger.info(f"Fallback reply: {reply}")
            return reply
        raise


def fetch_and_reply_comments(
    youtube,
    video_id: str,
    topic: str = "space",
    dry_run: bool = False,
    model_name: str = "gemini-1.5-flash",
) -> list[dict]:
    """
    Fetch recent comments on video_id, generate replies, post them.
    Returns list of reply records.
    """
    logger.info(f"Fetching comments for video: {video_id} ...")
    results = []

    try:
        response = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=MAX_REPLIES_PER_RUN * 3,  # Fetch extra to account for spam filtering
            order="relevance",
            textFormat="plainText",
        ).execute()
    except HttpError as e:
        logger.error(f"Failed to fetch comments: {e}")
        return results

    threads = response.get("items", [])
    logger.info(f"Fetched {len(threads)} comment threads.")

    replied_count = 0
    for thread in threads:
        if replied_count >= MAX_REPLIES_PER_RUN:
            break

        top = thread["snippet"]["topLevelComment"]["snippet"]
        comment_id = thread["snippet"]["topLevelComment"]["id"]
        comment_text = top.get("textDisplay", "")
        author = top.get("authorDisplayName", "Anonymous")

        logger.info(f"Comment by {author}: '{comment_text[:80]}'")

        if _is_spam(comment_text):
            continue

        reply_text = _generate_reply(comment_text, topic, model_name=model_name)

        if dry_run:
            logger.info(f"[DRY RUN] Would reply to {author}: {reply_text}")
            results.append({
                "comment_id": comment_id,
                "author": author,
                "comment": comment_text,
                "reply": reply_text,
                "posted": False,
                "dry_run": True,
            })
            replied_count += 1
            continue

        # Post reply
        try:
            youtube.comments().insert(
                part="snippet",
                body={
                    "snippet": {
                        "parentId": comment_id,
                        "textOriginal": reply_text,
                    }
                },
            ).execute()
            logger.info(f"✅ Reply posted to {author}.")
            results.append({
                "comment_id": comment_id,
                "author": author,
                "comment": comment_text,
                "reply": reply_text,
                "posted": True,
            })
            replied_count += 1
            time.sleep(random.uniform(2, 5))  # Polite delay between posts

        except HttpError as e:
            logger.error(f"Failed to post reply to {author}: {e}")
            results.append({
                "comment_id": comment_id,
                "author": author,
                "comment": comment_text,
                "reply": reply_text,
                "posted": False,
                "error": str(e),
            })

    logger.info(f"Replied to {replied_count} comments.")
    return results


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Auto-reply to YouTube comments using Gemini.")
    parser.add_argument("--video-id", default=None, help="YouTube video ID to reply to")
    parser.add_argument("--auto", action="store_true",
                        help="Read video ID from output/upload_result.json")
    parser.add_argument("--output", default="output/", help="Directory for upload_result.json")
    parser.add_argument("--model", default="gemini-1.5-flash")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    video_id = args.video_id
    if args.auto and not video_id:
        result_file = Path(args.output) / "upload_result.json"
        if result_file.exists():
            with open(result_file) as f:
                upload_result = json.load(f)
            video_id = upload_result.get("video_id")
            logger.info(f"Loaded video ID from upload_result.json: {video_id}")
        else:
            logger.error("--auto flag set but output/upload_result.json not found.")
            return

    if not video_id or video_id in ("DRY_RUN_NO_UPLOAD", "NO_CREDENTIALS"):
        logger.warning(f"Video ID is '{video_id}' — skipping comment replies.")
        return

    # Get YouTube service (reuse uploader helper)
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.upload_video import get_youtube_service

    youtube = get_youtube_service()
    if youtube is None and not args.dry_run:
        logger.error("No YouTube credentials — cannot fetch/post comments.")
        return

    # Load topic from script if available
    script_path = Path(args.output) / "script.json"
    topic = "space and astronomy"
    if script_path.exists():
        with open(script_path) as f:
            script_data = json.load(f)
        topic = script_data.get("apod_title", topic)

    results = fetch_and_reply_comments(
        youtube=youtube,
        video_id=video_id,
        topic=topic,
        dry_run=args.dry_run,
        model_name=args.model,
    )

    out_path = Path(args.output) / "comment_replies.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Reply log saved → {out_path}")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
