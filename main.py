"""
main.py — Orchestrator for The Universe YouTube Shorts pipeline.

Runs all 6 pipeline steps in order and passes outputs between them.
Exits with code 1 on any failure so GitHub Actions marks the run as failed.

Usage:
    python main.py                  # Full pipeline (production)
    python main.py --dry-run        # End-to-end with no real API calls
    python main.py --neo            # Use NEO asteroid data (Saturday Asteroid Watch)
    python main.py --date 2024-07-04  # Use a specific APOD date
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# ── Load local .env for development ───────────────────────────────────────────
load_dotenv()

# ── Structured logging setup ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("TheUniverse.Orchestrator")

# ── Pipeline imports ──────────────────────────────────────────────────────────
from src.fetch_content import fetch_apod, fetch_neo_week, save_json
from src.generate_script import generate_apod_script, generate_neo_script
from src.generate_audio import generate_audio
from src.build_video import build_video
from src.generate_metadata import generate_metadata
from src.upload_video import upload_to_youtube


def banner(msg: str) -> None:
    width = 60
    logger.info("=" * width)
    logger.info(f"  {msg}")
    logger.info("=" * width)


def is_asteroid_watch_day() -> bool:
    """Returns True on Saturdays (default Asteroid Watch day)."""
    return datetime.utcnow().weekday() == 5  # 5 = Saturday


def main(dry_run: bool = False, use_neo: bool = False, date: str = None) -> None:
    start_time = datetime.utcnow()
    banner("🌌 The Universe — YouTube Shorts Pipeline STARTED")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'PRODUCTION'} | "
                f"Content: {'NEO Asteroid Watch' if use_neo else 'APOD Daily'} | "
                f"Date: {date or 'today'}")

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    api_key_nasa = os.environ.get("NASA_API_KEY", "DEMO_KEY")
    if api_key_nasa == "DEMO_KEY":
        logger.warning("NASA_API_KEY not set — falling back to DEMO_KEY (rate-limited).")

    # ── Step 1: Fetch NASA content ────────────────────────────────────────────
    banner("Step 1/6 — Fetching NASA Content")
    if dry_run:
        from src.fetch_content import _DRY_RUN_APOD as apod_data
        save_json(apod_data, output_dir / "apod.json")
        logger.info("DRY RUN: Using fixture APOD data.")
        content_data = apod_data
        use_neo_actual = False
    elif use_neo or is_asteroid_watch_day():
        logger.info("Asteroid Watch mode — fetching NEO data.")
        content_data = fetch_neo_week(api_key_nasa, output_dir)
        save_json(content_data, output_dir / "neo.json")
        use_neo_actual = True
    else:
        content_data = fetch_apod(api_key_nasa, output_dir, date=date)
        save_json(content_data, output_dir / "apod.json")
        use_neo_actual = False
    logger.info("✅ Step 1 complete.")

    # ── Step 2: Generate script ───────────────────────────────────────────────
    banner("Step 2/6 — Generating Narration Script")
    if dry_run:
        from src.generate_script import _DRY_RUN_SCRIPT as script_data
        save_json(script_data, output_dir / "script.json")
        logger.info("DRY RUN: Using fixture script.")
    elif use_neo_actual:
        script_data = generate_neo_script(content_data)
        save_json(script_data, output_dir / "script.json")
    else:
        script_data = generate_apod_script(content_data)
        save_json(script_data, output_dir / "script.json")
    logger.info(f"✅ Step 2 complete. Script: {script_data.get('word_count', '?')} words.")
    logger.info(f"   Hook: '{script_data.get('hook_text', '')}'")

    # ── Step 3: Generate audio ────────────────────────────────────────────────
    banner("Step 3/6 — Generating TTS Audio")
    if dry_run:
        from src.generate_audio import _dry_run as audio_dry_run
        audio_result = audio_dry_run(output_dir)
        logger.info("DRY RUN: Placeholder audio created.")
    else:
        audio_result = generate_audio(
            script_path=output_dir / "script.json",
            output_dir=output_dir,
        )
    logger.info(f"✅ Step 3 complete. Duration: {audio_result.get('duration_seconds', '?')}s")

    # ── Step 4: Build video ───────────────────────────────────────────────────
    banner("Step 4/6 — Building 9:16 Short Video")
    video_output = output_dir / "final_video.mp4"
    if dry_run:
        from src.build_video import _dry_run as video_dry_run
        video_path = video_dry_run(video_output)
        logger.info("DRY RUN: Placeholder video created.")
    else:
        # Determine image path (could be .jpg, .jpeg, .png etc.)
        image_path = Path(content_data.get("local_image_path", "output/apod_image.jpg"))
        if not image_path.exists():
            # Fallback: find any image in output dir
            for ext in ["*.jpg", "*.jpeg", "*.png"]:
                matches = list(output_dir.glob(ext))
                if matches:
                    image_path = matches[0]
                    break
        video_path = build_video(
            image_path=image_path,
            audio_path=output_dir / "narration.mp3",
            vtt_path=output_dir / "narration.vtt",
            script_path=output_dir / "script.json",
            output_path=video_output,
        )
    logger.info(f"✅ Step 4 complete. Video: {video_path}")

    # ── Step 5: Generate metadata ─────────────────────────────────────────────
    banner("Step 5/6 — Generating Upload Metadata")
    # For NEO content, use a placeholder APOD-style dict for metadata generation
    if use_neo_actual:
        apod_for_meta = {
            "title": f"Asteroid Watch — {datetime.utcnow().strftime('%B %d')}",
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "copyright": "NASA JPL",
        }
    else:
        apod_for_meta = content_data

    if dry_run:
        from src.generate_metadata import _DRY_RUN_METADATA as metadata
        save_json(metadata, output_dir / "metadata.json")
        logger.info("DRY RUN: Using fixture metadata.")
    else:
        metadata = generate_metadata(apod_for_meta, script_data)
        save_json(metadata, output_dir / "metadata.json")
    logger.info(f"✅ Step 5 complete. Title: '{metadata.get('title', '')}'")

    # ── Step 6: Upload to YouTube ─────────────────────────────────────────────
    banner("Step 6/6 — Uploading to YouTube")
    upload_result = upload_to_youtube(
        video_path=video_output,
        metadata=metadata,
        dry_run=dry_run,
    )
    save_json(upload_result, output_dir / "upload_result.json")
    logger.info(f"✅ Step 6 complete. Video ID: {upload_result.get('video_id', 'N/A')}")
    logger.info(f"   URL: {upload_result.get('video_url', 'N/A')}")

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = (datetime.utcnow() - start_time).total_seconds()
    banner("🎉 PIPELINE COMPLETED SUCCESSFULLY")
    logger.info(f"Total time: {elapsed:.1f}s")
    logger.info(f"Title:      {metadata.get('title', '')}")
    logger.info(f"Video URL:  {upload_result.get('video_url', 'N/A')}")
    logger.info(f"Mode:       {'DRY RUN' if dry_run else 'PRODUCTION'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The Universe — YouTube Shorts Pipeline Orchestrator")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run end-to-end with no real API calls or uploads")
    parser.add_argument("--neo", action="store_true",
                        help="Force NEO Asteroid Watch mode (otherwise auto-detects Saturday)")
    parser.add_argument("--date", default=None,
                        help="Specific APOD date to use (YYYY-MM-DD)")
    args = parser.parse_args()

    try:
        main(dry_run=args.dry_run, use_neo=args.neo, date=args.date)
    except Exception as e:
        logger.exception(f"❌ PIPELINE FAILED: {e}")
        sys.exit(1)
