"""
reply_comments.py — Auto-reply to YouTube comments with BTS ARMY persona.

Uses the Gemini API (GEMINI_API_KEY — already in GitHub Secrets) to generate
warm, humanized, natural-sounding replies from a passionate BTS ARMY perspective.

Skips:
  - Spam / self-promo comments
  - Comments the channel has already replied to
  - Very short comments (< 15 chars)

Usage:
    python src/reply_comments.py --video-id <YT_VIDEO_ID>
    python src/reply_comments.py --video-id <YT_VIDEO_ID> --dry-run
    python src/reply_comments.py --auto          # reads video_id from output/upload_result.json
    python src/reply_comments.py --channel-scan  # scan latest channel videos for unreplied comments
"""

import argparse
import json
import logging
import os
import random
import re
import requests
import time
from pathlib import Path
from typing import Optional, List

from googleapiclient.errors import HttpError

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("reply_comments")

# ── Config ─────────────────────────────────────────────────────────────────────
MIN_COMMENT_LENGTH = 15
MAX_REPLIES_PER_VIDEO = 10
MAX_VIDEOS_TO_SCAN = 5

SPAM_KEYWORDS = [
    "subscribe back", "sub4sub", "check out my", "visit my channel",
    "click here", "free money", "earn $", "http://", "bit.ly",
    "follow me back", "promo", "discount", "giveaway", "dm me",
    "whatsapp", "telegram", "onlyfans", "crypto", "nft",
]

# ── Gemini Reply Prompt ────────────────────────────────────────────────────────
REPLY_SYSTEM_PROMPT = """You are a real BTS ARMY who runs a fan YouTube Shorts channel called "BTS Spotlight".
You genuinely love BTS and their music. You write replies to comments on your videos.

Your personality:
- Warm, friendly, slightly excitable but never over-the-top
- You type like a real person, not a corporate account
- You sometimes use lowercase for a casual vibe
- You're knowledgeable about BTS (members, songs, albums, inside jokes)
- You show genuine appreciation when someone comments

Rules:
1. Keep replies SHORT — 1-2 sentences, max 25 words.
2. Directly respond to what the person actually said.
3. Use 1 emoji max (usually 💜 or 🫰 or 🥺 or 😭 — ARMY favorites).
4. NEVER ask people to subscribe, like, or follow.
5. NEVER be negative about any member or any other group.
6. NEVER mention controversy, dating rumors, military service complaints, or politics.
7. Vary your tone — don't start every reply the same way.
8. Sound HUMAN. Real people don't write perfectly formatted corporate responses.
9. If someone mentions their bias, acknowledge it warmly.
10. If the comment is in a language other than English, reply in that same language.
"""

REPLY_USER_TEMPLATE = """The video was about: "{topic}"

This fan commented: "{comment}"

Write a natural, warm reply as a fellow ARMY (1-2 sentences, max 25 words, 1 emoji max). Sound like a real person, not a bot."""


# ── Gemini API ─────────────────────────────────────────────────────────────────
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


def _get_gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is not set.")
    return key


def _generate_reply_gemini(comment_text: str, topic: str) -> str:
    """Generate a humanized BTS ARMY reply using Gemini API (free tier)."""
    api_key = _get_gemini_key()
    prompt = REPLY_USER_TEMPLATE.format(topic=topic, comment=comment_text[:300])

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": REPLY_SYSTEM_PROMPT + "\n\n" + prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 80,
            "topP": 0.9,
        },
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                f"{GEMINI_API_URL}?key={api_key}",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            # Extract text from Gemini response
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    reply = parts[0].get("text", "").strip()
                    # Clean up: remove quotes Gemini sometimes wraps around replies
                    reply = reply.strip('"').strip("'").strip()
                    if reply:
                        logger.info(f"💬 Generated reply: {reply}")
                        return reply

            logger.warning(f"Gemini returned empty reply on attempt {attempt + 1}")

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                wait = 5 * (attempt + 1)
                logger.warning(f"Gemini rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                logger.warning(f"Gemini API error on attempt {attempt + 1}: {e}")
                time.sleep(2)
        except Exception as e:
            logger.warning(f"Gemini request failed on attempt {attempt + 1}: {e}")
            time.sleep(2)

    # Fallback: pick a generic warm reply if Gemini fails completely
    return random.choice([
        "thank you so much for watching! 💜",
        "this made my day, thank you ARMY 💜",
        "you're the best, thanks for the love! 🫰",
        "ahhh thank you for commenting! 💜",
    ])


# ── YouTube helpers ────────────────────────────────────────────────────────────

def _get_youtube_service():
    """Build YouTube API service with comment scopes."""
    import base64
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds_b64 = os.environ.get("YOUTUBE_CREDENTIALS_JSON", "").strip()
    if not creds_b64:
        logger.warning("YOUTUBE_CREDENTIALS_JSON not set.")
        return None

    try:
        decoded = base64.b64decode(creds_b64).decode("utf-8")
        creds_data = json.loads(decoded)
    except Exception as e:
        logger.error(f"Failed to decode YOUTUBE_CREDENTIALS_JSON: {e}")
        return None

    # Support flat or nested credential formats
    if "refresh_token" in creds_data:
        inner = creds_data
    elif "installed" in creds_data:
        inner = creds_data["installed"]
        inner["refresh_token"] = creds_data.get("refresh_token", inner.get("refresh_token"))
    elif "web" in creds_data:
        inner = creds_data["web"]
        inner["refresh_token"] = creds_data.get("refresh_token", inner.get("refresh_token"))
    else:
        logger.error("Cannot determine credential structure.")
        return None

    if not inner.get("refresh_token"):
        logger.error("No refresh_token found in credentials.")
        return None

    credentials = Credentials(
        token=inner.get("access_token"),
        refresh_token=inner["refresh_token"],
        client_id=inner.get("client_id"),
        client_secret=inner.get("client_secret"),
        token_uri=inner.get("token_uri", "https://oauth2.googleapis.com/token"),
    )
    logger.info("YouTube credentials loaded for comment replies.")
    return build("youtube", "v3", credentials=credentials)


def _get_channel_id(youtube) -> Optional[str]:
    """Get the authenticated channel's ID."""
    try:
        resp = youtube.channels().list(part="id", mine=True).execute()
        items = resp.get("items", [])
        if items:
            return items[0]["id"]
    except HttpError as e:
        logger.error(f"Failed to get channel ID: {e}")
    return None


def _get_recent_video_ids(youtube, channel_id: str, max_results: int = 5) -> List[str]:
    """Get the most recent video IDs from the channel."""
    try:
        resp = youtube.search().list(
            part="id",
            channelId=channel_id,
            order="date",
            maxResults=max_results,
            type="video",
        ).execute()
        return [item["id"]["videoId"] for item in resp.get("items", []) if item["id"].get("videoId")]
    except HttpError as e:
        logger.error(f"Failed to list channel videos: {e}")
        return []


def _is_spam(comment_text: str) -> bool:
    """Return True if the comment looks like spam."""
    lower = comment_text.lower()
    for kw in SPAM_KEYWORDS:
        if kw in lower:
            logger.info(f"⏭️  Skipping spam (matched '{kw}'): {comment_text[:50]}")
            return True
    if len(comment_text.strip()) < MIN_COMMENT_LENGTH:
        logger.info(f"⏭️  Skipping short comment: '{comment_text[:40]}'")
        return True
    return False


def fetch_and_reply_comments(
    youtube,
    video_id: str,
    topic: str = "BTS",
    dry_run: bool = False,
) -> List[dict]:
    """
    Fetch comments on video_id, skip already-replied ones,
    generate natural ARMY replies, and post them.
    """
    logger.info(f"📺 Processing comments for video: {video_id}")
    results = []
    replied_count = 0

    # Get our channel ID so we can detect our own replies
    channel_id = _get_channel_id(youtube)
    if channel_id:
        logger.info(f"Channel ID: {channel_id}")

    # Fetch comment threads
    try:
        response = youtube.commentThreads().list(
            part="snippet,replies",
            videoId=video_id,
            maxResults=min(100, MAX_REPLIES_PER_VIDEO * 5),
            order="relevance",
            textFormat="plainText",
        ).execute()
    except HttpError as e:
        if "commentsDisabled" in str(e):
            logger.warning(f"Comments disabled on video {video_id}.")
        else:
            logger.error(f"Failed to fetch comments: {e}")
        return results

    threads = response.get("items", [])
    logger.info(f"Found {len(threads)} comment threads.")

    for thread in threads:
        if replied_count >= MAX_REPLIES_PER_VIDEO:
            logger.info(f"Reached max replies ({MAX_REPLIES_PER_VIDEO}), stopping.")
            break

        snippet = thread["snippet"]
        top_comment = snippet["topLevelComment"]["snippet"]
        comment_id = snippet["topLevelComment"]["id"]
        comment_text = top_comment.get("textDisplay", "")
        author = top_comment.get("authorDisplayName", "Someone")
        author_channel = top_comment.get("authorChannelId", {}).get("value", "")

        # Skip our own comments
        if channel_id and author_channel == channel_id:
            logger.info(f"⏭️  Skipping own comment by {author}")
            continue

        # Skip spam
        if _is_spam(comment_text):
            continue

        # Check if we already replied to this comment thread
        already_replied = False
        if channel_id:
            replies_data = thread.get("replies", {}).get("comments", [])
            for reply in replies_data:
                reply_channel = reply.get("snippet", {}).get("authorChannelId", {}).get("value", "")
                if reply_channel == channel_id:
                    already_replied = True
                    break

            # If replies weren't fully loaded, check via API for threads with many replies
            if not already_replied and snippet.get("totalReplyCount", 0) > len(replies_data):
                try:
                    all_replies = youtube.comments().list(
                        part="snippet",
                        parentId=comment_id,
                        maxResults=100,
                        textFormat="plainText",
                    ).execute()
                    for r in all_replies.get("items", []):
                        rc = r.get("snippet", {}).get("authorChannelId", {}).get("value", "")
                        if rc == channel_id:
                            already_replied = True
                            break
                except HttpError:
                    pass

        if already_replied:
            logger.info(f"⏭️  Already replied to {author}: '{comment_text[:40]}...'")
            continue

        # Generate reply
        logger.info(f"💬 {author}: '{comment_text[:60]}'")
        reply_text = _generate_reply_gemini(comment_text, topic)

        if dry_run:
            logger.info(f"[DRY RUN] Would reply → {reply_text}")
            results.append({
                "video_id": video_id,
                "comment_id": comment_id,
                "author": author,
                "comment": comment_text,
                "reply": reply_text,
                "posted": False,
                "dry_run": True,
            })
            replied_count += 1
            continue

        # Post the reply
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

            logger.info(f"✅ Replied to {author}: {reply_text}")
            results.append({
                "video_id": video_id,
                "comment_id": comment_id,
                "author": author,
                "comment": comment_text,
                "reply": reply_text,
                "posted": True,
            })
            replied_count += 1

            # Humanized delay between replies (2–6 seconds)
            delay = random.uniform(2.0, 6.0)
            logger.info(f"⏳ Waiting {delay:.1f}s before next reply...")
            time.sleep(delay)

        except HttpError as e:
            logger.error(f"❌ Failed to reply to {author}: {e}")
            results.append({
                "video_id": video_id,
                "comment_id": comment_id,
                "author": author,
                "comment": comment_text,
                "reply": reply_text,
                "posted": False,
                "error": str(e),
            })

    logger.info(f"💜 Finished: replied to {replied_count} comments on video {video_id}")
    return results


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Auto-reply to YouTube comments as a BTS ARMY using Gemini."
    )
    parser.add_argument("--video-id", default=None, help="YouTube video ID to reply to")
    parser.add_argument("--auto", action="store_true",
                        help="Read video ID from output/upload_result.json")
    parser.add_argument("--channel-scan", action="store_true",
                        help="Scan latest channel videos for unreplied comments")
    parser.add_argument("--output", default="output/", help="Output directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate replies but don't post them")
    args = parser.parse_args()

    # Build YouTube service
    youtube = _get_youtube_service()
    if youtube is None and not args.dry_run:
        logger.error("No YouTube credentials — cannot fetch/post comments.")
        return

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results = []

    # Determine which videos to process
    video_ids = []

    if args.video_id:
        video_ids = [args.video_id]

    elif args.auto:
        # Try to load from upload_result.json
        result_file = output_dir / "upload_result.json"
        if result_file.exists():
            with open(result_file) as f:
                upload_result = json.load(f)
            vid = upload_result.get("video_id", "")
            if vid and vid not in ("DRY_RUN_NO_UPLOAD", "NO_CREDENTIALS"):
                video_ids = [vid]
                logger.info(f"Loaded video ID from upload_result.json: {vid}")
            else:
                logger.warning(f"upload_result.json has no valid video ID ('{vid}').")
        else:
            logger.warning("upload_result.json not found — falling back to channel scan.")
            args.channel_scan = True

    if args.channel_scan or (not video_ids and not args.video_id):
        # Scan latest channel videos
        logger.info("🔍 Scanning latest channel videos for unreplied comments...")
        channel_id = _get_channel_id(youtube)
        if channel_id:
            video_ids = _get_recent_video_ids(youtube, channel_id, MAX_VIDEOS_TO_SCAN)
            logger.info(f"Found {len(video_ids)} recent videos to scan.")
        else:
            logger.error("Could not determine channel ID for scanning.")

    if not video_ids:
        logger.warning("No video IDs to process. Exiting.")
        return

    # Load topic from script.json if available
    topic = "BTS updates and highlights"
    script_path = output_dir / "script.json"
    if script_path.exists():
        try:
            with open(script_path) as f:
                script_data = json.load(f)
            topic = script_data.get("hook_text") or script_data.get("title", topic)
        except Exception:
            pass

    # Process each video
    for vid in video_ids:
        logger.info(f"\n{'='*50}")
        logger.info(f"Processing video: https://youtube.com/shorts/{vid}")
        logger.info(f"{'='*50}")

        results = fetch_and_reply_comments(
            youtube=youtube,
            video_id=vid,
            topic=topic,
            dry_run=args.dry_run,
        )
        all_results.extend(results)

    # Save results
    out_path = output_dir / "comment_replies.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    total_posted = sum(1 for r in all_results if r.get("posted"))
    total_dry = sum(1 for r in all_results if r.get("dry_run"))
    logger.info(f"\n💜 Summary: {total_posted} replies posted, {total_dry} dry-run, "
                f"{len(all_results)} total across {len(video_ids)} video(s)")
    logger.info(f"Reply log saved → {out_path}")


if __name__ == "__main__":
    main()
