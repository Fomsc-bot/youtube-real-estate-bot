"""
upload_video.py — Step 6 of The Universe pipeline.

Uploads the assembled Short to YouTube via the Data API v3.
Uses OAuth2 credentials (client_id, client_secret, refresh_token)
stored as the YOUTUBE_CREDENTIALS_JSON GitHub Secret (same format
as the previous real-estate implementation — base64-encoded JSON).

Usage:
    python src/upload_video.py --video output/final_video.mp4 --metadata output/metadata.json
    python src/upload_video.py --video output/final_video.mp4 --metadata output/metadata.json --dry-run
"""

import argparse
import base64
import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Optional

import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
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
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=2, max=30),
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
logger = logging.getLogger("upload_video")

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"

# YouTube quota error codes that are retryable
RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
QUOTA_EXCEEDED_CODE = 403


def get_youtube_service() -> Optional[object]:
    """
    Build YouTube API service from YOUTUBE_CREDENTIALS_JSON environment variable.
    The secret is a base64-encoded JSON containing:
      { "client_id": "...", "client_secret": "...", "refresh_token": "...", "token_uri": "..." }

    Returns the YouTube service object, or None if credentials are not configured.
    """
    creds_b64 = os.environ.get("YOUTUBE_CREDENTIALS_JSON")
    if not creds_b64:
        logger.warning(
            "YOUTUBE_CREDENTIALS_JSON not set — running in DRY RUN mode (no upload)."
        )
        return None

    try:
        decoded = base64.b64decode(creds_b64).decode("utf-8")
        creds_data = json.loads(decoded)
    except Exception as e:
        logger.error(f"Failed to decode YOUTUBE_CREDENTIALS_JSON: {e}")
        return None

    try:
        # Support both flat and nested formats (web/installed client secrets)
        if "refresh_token" in creds_data:
            inner = creds_data
        elif "installed" in creds_data:
            inner = creds_data["installed"]
        elif "web" in creds_data:
            inner = creds_data["web"]
        else:
            raise ValueError("Cannot determine credential structure in YOUTUBE_CREDENTIALS_JSON")

        credentials = Credentials(
            token=inner.get("access_token"),
            refresh_token=inner.get("refresh_token"),
            client_id=inner.get("client_id"),
            client_secret=inner.get("client_secret"),
            token_uri=inner.get("token_uri", TOKEN_URI),
        )
        logger.info("YouTube OAuth2 credentials loaded successfully.")
        return build("youtube", "v3", credentials=credentials)

    except Exception as e:
        logger.error(f"Failed to initialize YouTube API client: {e}")
        return None


def upload_to_youtube(
    video_path: Path,
    metadata: dict,
    dry_run: bool = False,
) -> dict:
    """
    Upload video to YouTube with resumable chunked upload.
    Returns dict with video_id and video_url.
    """
    title = metadata.get("title", "Today in Space #Shorts")
    description = metadata.get("description", "")
    tags = metadata.get("tags", [])
    category_id = metadata.get("categoryId", "28")
    privacy = metadata.get("privacyStatus", "public")
    made_for_kids = metadata.get("selfDeclaredMadeForKids", False)
    contains_synthetic = metadata.get("containsSyntheticMedia", False)

    logger.info(f"Preparing upload: '{title}'")
    logger.info(f"Video path: {video_path} ({video_path.stat().st_size / 1024 / 1024:.1f} MB)")

    if dry_run:
        logger.info("DRY RUN — skipping actual YouTube upload.")
        return {
            "video_id": "DRY_RUN_NO_UPLOAD",
            "video_url": "https://www.youtube.com/shorts/DRY_RUN_NO_UPLOAD",
            "title": title,
            "dry_run": True,
        }

    youtube = get_youtube_service()
    if youtube is None:
        logger.warning("No YouTube service available — treating as dry run.")
        return {
            "video_id": "NO_CREDENTIALS",
            "video_url": "https://www.youtube.com/shorts/NO_CREDENTIALS",
            "title": title,
            "dry_run": True,
        }

    # Build the video resource body
    video_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
            "defaultLanguage": metadata.get("defaultLanguage", "en"),
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": made_for_kids,
            "containsSyntheticMedia": contains_synthetic,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        chunksize=5 * 1024 * 1024,   # 5 MB chunks
        resumable=True,
        mimetype="video/mp4",
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=video_body,
        media_body=media,
    )

    # Resumable upload with retry on server errors
    max_retries = 5
    retry_count = 0
    response = None

    logger.info("Starting resumable upload ...")
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info(f"Upload progress: {pct}%")
        except HttpError as e:
            if e.resp.status in RETRYABLE_STATUS_CODES:
                retry_count += 1
                if retry_count > max_retries:
                    raise
                sleep_s = random.uniform(1, 2 ** retry_count)
                logger.warning(
                    f"YouTube server error {e.resp.status}. "
                    f"Retry {retry_count}/{max_retries} in {sleep_s:.1f}s ..."
                )
                time.sleep(sleep_s)
            elif e.resp.status == QUOTA_EXCEEDED_CODE:
                logger.error(
                    "YouTube API quota exceeded (403). "
                    "The upload will not be retried. Check your Google Cloud quota."
                )
                raise
            else:
                logger.error(f"YouTube API error {e.resp.status}: {e.content}")
                raise
        except (requests.exceptions.RequestException, IOError) as e:
            retry_count += 1
            if retry_count > max_retries:
                raise
            sleep_s = random.uniform(1, 2 ** retry_count)
            logger.warning(f"Network error: {e}. Retry {retry_count}/{max_retries} in {sleep_s:.1f}s ...")
            time.sleep(sleep_s)

    video_id = response.get("id", "unknown")
    video_url = f"https://www.youtube.com/shorts/{video_id}"
    logger.info(f"✅ Upload complete! Video ID: {video_id}")
    logger.info(f"🔗 URL: {video_url}")

    return {
        "video_id": video_id,
        "video_url": video_url,
        "title": title,
        "dry_run": False,
    }


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Upload Short to YouTube via Data API v3.")
    parser.add_argument("--video", default="output/final_video.mp4")
    parser.add_argument("--metadata", default="output/metadata.json")
    parser.add_argument("--output", default="output/upload_result.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log upload payload but skip actual YouTube call")
    args = parser.parse_args()

    with open(args.metadata) as f:
        metadata = json.load(f)

    result = upload_to_youtube(
        video_path=Path(args.video),
        metadata=metadata,
        dry_run=args.dry_run,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)
    logger.info(f"Upload result saved → {output_path}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
