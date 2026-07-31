"""
main.py — Viral YouTube Shorts Pipeline Orchestrator

Integrates MoneyPrinterTurbo (viral script hooks, sentence keyword alignment,
multi-clip stock video fetching, background audio ducking) and Remotion (dynamic
karaoke captions, subscriber conversion badge overlay, video progress bars).

Usage:
    python main.py                           # Default Real Estate Niche
    python main.py --niche real_estate       # Luxury Mansions & Real Estate Secrets
    python main.py --niche space             # NASA / Astronomy / Deep Space Facts
    python main.py --dry-run                 # End-to-end dry run (no API calls)
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ViralShorts.Orchestrator")

# ── Pipeline Imports ──────────────────────────────────────────────────────────
from src.generate_assets import ensure_assets
from src.generate_script import generate_viral_script, get_fallback_script
from src.fetch_content import fetch_multi_scene_content, save_json, fetch_apod
from src.generate_audio import generate_audio
from src.build_video import build_video
from src.generate_metadata import generate_metadata
from src.upload_video import upload_to_youtube


def banner(msg: str) -> None:
    width = 65
    logger.info("=" * width)
    logger.info(f"  {msg}")
    logger.info("=" * width)


def main(
    dry_run: bool = False,
    niche: str = "real_estate",
    topic: str = None,
    date: str = None,
) -> None:
    start_time = datetime.now(timezone.utc)
    ensure_assets()

    banner("🚀 VIRAL YOUTUBE SHORTS PIPELINE — MoneyPrinterTurbo + Remotion")
    logger.info(
        f"Mode: {'DRY RUN' if dry_run else 'PRODUCTION'} | "
        f"Niche: {niche.upper()} | "
        f"Topic: {topic or 'Auto-generated Viral Topic'}"
    )

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # ── Step 1: Generate Script (MoneyPrinterTurbo Hook Engine) ───────────────
    banner("Step 1/6 — Generating Viral Script & Sentence Keywords")
    if dry_run:
        from src.generate_script import _DRY_RUN_SCRIPT as script_data
        save_json(script_data, output_dir / "script.json")
        logger.info("DRY RUN: Using fixture script data.")
    else:
        source_content = None
        if niche == "space":
            nasa_key = os.environ.get("NASA_API_KEY") or "DEMO_KEY"
            try:
                source_content = fetch_apod(nasa_key, output_dir, date=date)
                save_json(source_content, output_dir / "apod.json")
            except Exception as e:
                logger.warning(f"NASA APOD fetch fallback: {e}")

        script_data = generate_viral_script(
            niche=niche, topic=topic, source_content=source_content
        )
        save_json(script_data, output_dir / "script.json")

    logger.info(f"✅ Step 1 complete. Script ({script_data.get('word_count', '?')} words):")
    logger.info(f"   Hook: '{script_data.get('hook_text', '')}'")

    # ── Step 2: Fetch Multi-Clip Visual Content (Pexels / Stock Media) ────────
    banner("Step 2/6 — Fetching Multi-Clip Visual Assets (Pexels API)")
    if dry_run:
        from src.fetch_content import _DRY_RUN_SCENES as scenes_data
        save_json({"scenes": scenes_data}, output_dir / "scenes_meta.json")
        for sc in scenes_data:
            from src.fetch_content import create_fallback_scene_image
            create_fallback_scene_image(sc["text"], sc["keyword"], Path(sc["media_path"]))
        logger.info("DRY RUN: Using fixture scenes visual assets.")
    else:
        scenes_data = fetch_multi_scene_content(script_data, output_dir)
    logger.info(f"✅ Step 2 complete. Fetched {len(scenes_data)} visual clips.")

    # ── Step 3: Generate Audio & WebVTT Karaoke Timestamps ────────────────────
    banner("Step 3/6 — Generating Speech Audio & Karaoke Timestamps")
    if dry_run:
        from src.generate_audio import _dry_run as audio_dry_run
        audio_meta = audio_dry_run(output_dir)
        logger.info("DRY RUN: Placeholder audio created.")
    else:
        audio_meta = generate_audio(
            script_path=output_dir / "script.json",
            output_dir=output_dir,
        )
    logger.info(f"✅ Step 3 complete. Audio duration: {audio_meta.get('duration_seconds', '?')}s")

    # ── Step 4: Build Video (Remotion Motion Graphics Compositor) ─────────────
    banner("Step 4/6 — Compositing Remotion Motion Graphics 9:16 Video")
    video_output = output_dir / "final_video.mp4"
    if dry_run:
        from src.build_video import _dry_run as video_dry_run
        video_path = video_dry_run(video_output)
        logger.info("DRY RUN: Placeholder video created.")
    else:
        video_path = build_video(
            image_path=output_dir / "apod_image.jpg",
            audio_path=output_dir / "narration.mp3",
            vtt_path=output_dir / "narration.vtt",
            script_path=output_dir / "script.json",
            output_path=video_output,
        )
    logger.info(f"✅ Step 4 complete. Video: {video_path}")

    # ── Step 5: Generate Viral Metadata & Pinned Comment ──────────────────────
    banner("Step 5/6 — Generating High-CTR Metadata & Pinned Comment")
    if dry_run:
        from src.generate_metadata import _DRY_RUN_METADATA as metadata
        save_json(metadata, output_dir / "metadata.json")
    else:
        metadata = generate_metadata(script_data)
        save_json(metadata, output_dir / "metadata.json")
    logger.info(f"✅ Step 5 complete. Title: '{metadata.get('title', '')}'")

    # ── Step 6: Upload to YouTube ─────────────────────────────────────────────
    banner("Step 6/6 — Uploading Video & Pinning Subscriber Comment")
    upload_result = upload_to_youtube(
        video_path=video_output,
        metadata=metadata,
        dry_run=dry_run,
    )
    save_json(upload_result, output_dir / "upload_result.json")
    logger.info(f"✅ Step 6 complete. Video ID: {upload_result.get('video_id', 'N/A')}")
    logger.info(f"   URL: {upload_result.get('video_url', 'N/A')}")

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    banner("🎉 VIRAL PIPELINE COMPLETED SUCCESSFULLY")
    logger.info(f"Total time:  {elapsed:.1f}s")
    logger.info(f"Niche:       {niche.upper()}")
    logger.info(f"Title:       {metadata.get('title', '')}")
    logger.info(f"Video URL:   {upload_result.get('video_url', 'N/A')}")
    logger.info(f"Pinned CTA:  {metadata.get('pinned_comment', 'N/A')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Viral YouTube Shorts Pipeline Orchestrator")
    parser.add_argument("--dry-run", action="store_true", help="Run end-to-end dry run without API calls")
    parser.add_argument("--niche", default="real_estate", choices=["real_estate", "space"], help="Content niche")
    parser.add_argument("--topic", default=None, help="Specific topic prompt")
    parser.add_argument("--date", default=None, help="APOD date for space niche (YYYY-MM-DD)")
    args = parser.parse_args()

    try:
        main(dry_run=args.dry_run, niche=args.niche, topic=args.topic, date=args.date)
    except Exception as e:
        logger.exception(f"❌ PIPELINE FAILED: {e}")
        sys.exit(1)
