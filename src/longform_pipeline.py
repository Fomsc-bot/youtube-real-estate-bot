"""Prepare and optionally publish a source-based BTS long-form fan video."""

import json
import logging
import os
from pathlib import Path

from googleapiclient.http import MediaFileUpload

from src.build_longform_video import create_thumbnail, render_longform_video
from src.fetch_longform_assets import fetch_longform_photos
from src.generate_audio import generate_audio
from src.generate_longform import generate_longform_script
from src.research_longform import obtain_longform_research
from src.upload_video import get_youtube_service, upload_to_youtube

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("longform_pipeline")


def _timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}" if total >= 3600 else f"{total // 60:02d}:{total % 60:02d}"


def _build_metadata(script: dict, photos: list[dict], audio_duration: float) -> dict:
    chapters = script["chapters"]
    total_words = max(1, script["word_count"])
    elapsed = 0.0
    chapter_lines = []
    for chapter in chapters:
        chapter_lines.append(f"{_timestamp(elapsed)} {chapter['title']}")
        elapsed += audio_duration * len(chapter["narration"].split()) / total_words

    references = "\n".join(
        f"[{index}] {url}" for index, url in enumerate(script["source_urls"], start=1)
    )
    photo_credits = "\n".join(
        f"- {photo['file']} — {photo['creator']} — {photo['license']}: {photo['source_url']}"
        for photo in photos
    )
    description = "\n\n".join([
        "Thoughtful, source-based BTS fan commentary about the public artistry and moments ARMY admire. This episode shares a fan perspective; it does not make claims about members' private lives or relationships.",
        "Subscribe for original BTS fan stories and context.\n\n" + script["viewer_question"],
        "CHAPTERS\n" + "\n".join(chapter_lines),
        "RESEARCH SOURCES\n" + references,
        "PHOTO CREDITS AND LICENSES\n" + photo_credits,
        "#BTS #ARMY #Kpop",
    ])
    tags = ["BTS", "BTS ARMY", "Bangtan Sonyeondan", "K-pop commentary", "BTS fan discussion", "BTS members", "ARMY stories", "fan culture"]
    return {
        "title": script["title"],
        "description": description,
        "tags": tags,
        "categoryId": "24",
        "privacyStatus": "public",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,
        "defaultLanguage": "en",
        "niche": "bts_longform",
    }


def _set_thumbnail(video_id: str, thumbnail_path: Path) -> None:
    youtube = get_youtube_service()
    if youtube is None:
        raise RuntimeError("YouTube credentials are required to set the long-form thumbnail.")
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg"),
    ).execute()
    logger.info("Set custom long-form thumbnail.")


def run_longform_pipeline(topic: str, research_notes: str, source_urls: str, dry_run: bool = True) -> dict:
    output_dir = Path("output/longform")
    output_dir.mkdir(parents=True, exist_ok=True)
    if not (topic.strip() and research_notes.strip() and source_urls.strip()):
        topic, research_notes, source_urls = obtain_longform_research(
            output_dir / "research.json"
        )
    script = generate_longform_script(
        topic=topic,
        research_notes=research_notes,
        source_text=source_urls,
        output_path=output_dir / "script.json",
    )
    photos = fetch_longform_photos(output_dir / "photos", count=len(script["chapters"]))
    (output_dir / "photo_credits.json").write_text(
        json.dumps(photos, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    audio_meta = generate_audio(output_dir / "script.json", output_dir)
    video_path = render_longform_video(
        photos=photos,
        chapters=script["chapters"],
        narration=script["narration"],
        audio_path=Path(audio_meta["mp3_path"]),
        audio_duration=float(audio_meta["duration_seconds"]),
        output_path=output_dir / "longform_video.mp4",
    )
    thumbnail_path = create_thumbnail(
        Path(photos[0]["local_path"]), script["thumbnail_text"], output_dir / "thumbnail.jpg"
    )
    metadata = _build_metadata(script, photos, float(audio_meta["duration_seconds"]))
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    result = upload_to_youtube(video_path=video_path, metadata=metadata, dry_run=dry_run)
    video_id = result.get("video_id")
    if not dry_run and video_id and video_id not in {"unknown", "DRY_RUN_NO_UPLOAD", "NO_CREDENTIALS"}:
        result["video_url"] = f"https://www.youtube.com/watch?v={video_id}"
        try:
            _set_thumbnail(video_id, thumbnail_path)
        except Exception as error:
            # The video upload has already succeeded. Keep its ID and URL in
            # the artifact even if YouTube rejects the optional thumbnail.
            logger.exception("Video uploaded, but custom thumbnail upload failed.")
            result["thumbnail_error"] = str(error)
    result["title"] = metadata["title"]
    result["thumbnail_path"] = str(thumbnail_path)
    result["video_path"] = str(video_path)
    (output_dir / "upload_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build and upload one source-based BTS long-form video.")
    parser.add_argument("--dry-run", action="store_true", default=os.environ.get("LONGFORM_DRY_RUN", "true").lower() == "true")
    parser.add_argument("--topic", default=os.environ.get("LONGFORM_TOPIC", ""))
    parser.add_argument("--research-notes", default=os.environ.get("LONGFORM_RESEARCH_NOTES", ""))
    parser.add_argument("--source-urls", default=os.environ.get("LONGFORM_SOURCE_URLS", ""))
    args = parser.parse_args()
    result = run_longform_pipeline(args.topic, args.research_notes, args.source_urls, args.dry_run)
    logger.info("Long-form pipeline completed: %s", json.dumps(result, ensure_ascii=False))
