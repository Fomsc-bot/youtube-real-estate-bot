"""
generate_audio.py — Step 3 of The Universe pipeline.

Converts the narration script to speech using Microsoft edge-tts.
Outputs an MP3 audio file and a WebVTT caption file with word-level
timestamps for animated caption sync in the video builder.

Voice: en-US-AriaNeural — distinctive, warm, engaging. Not the generic default.

Usage:
    python src/generate_audio.py --script output/script.json
    python src/generate_audio.py --script output/script.json --output output/ --voice en-US-GuyNeural
    python src/generate_audio.py --dry-run
"""

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import edge_tts
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
logger = logging.getLogger("generate_audio")

# ── Config ─────────────────────────────────────────────────────────────────────
DEFAULT_VOICE = "en-US-AriaNeural"
DEFAULT_RATE = "+5%"      # Slightly faster than neutral for Shorts pacing
DEFAULT_PITCH = "+0Hz"


# ── Core generation ────────────────────────────────────────────────────────────
async def _generate_tts(
    text: str,
    mp3_path: Path,
    vtt_path: Path,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = DEFAULT_PITCH,
) -> None:
    """Run edge-tts and produce MP3 + VTT with word-level timestamps."""
    mp3_path.parent.mkdir(parents=True, exist_ok=True)

    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
    submaker = edge_tts.SubMaker()

    logger.info(f"Generating TTS with voice={voice}, rate={rate} ...")

    with open(mp3_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.create_sub(chunk["text"], chunk["offset"], chunk["duration"])

    logger.info(f"Audio saved → {mp3_path}")

    # Write VTT subtitle file with word-level timestamps
    vtt_content = submaker.generate_subs(words_in_cue=1)
    with open(vtt_path, "w", encoding="utf-8") as vtt_file:
        vtt_file.write(vtt_content)
    logger.info(f"Word-level VTT saved → {vtt_path}")


def _get_audio_duration(mp3_path: Path) -> float:
    """Use ffprobe to get audio duration in seconds."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", str(mp3_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        info = json.loads(result.stdout)
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "audio":
                return float(stream.get("duration", 0))
    except Exception as e:
        logger.warning(f"Could not determine audio duration: {e}")
    return 0.0


def generate_audio(
    script_path: Path,
    output_dir: Path,
    voice: str = DEFAULT_VOICE,
) -> dict:
    """
    Generate audio from script.json.
    Returns dict with paths to mp3 and vtt files, plus duration.
    """
    with open(script_path) as f:
        script_data = json.load(f)

    narration = script_data.get("narration", "")
    if not narration:
        raise ValueError(f"No 'narration' field found in {script_path}")

    logger.info(f"Narration text ({len(narration.split())} words): {narration[:80]}...")

    mp3_path = output_dir / "narration.mp3"
    vtt_path = output_dir / "narration.vtt"

    asyncio.run(_generate_tts(narration, mp3_path, vtt_path, voice=voice))

    duration = _get_audio_duration(mp3_path)
    logger.info(f"Audio duration: {duration:.2f}s")

    result = {
        "mp3_path": str(mp3_path),
        "vtt_path": str(vtt_path),
        "duration_seconds": round(duration, 3),
        "voice": voice,
        "narration": narration,
    }

    # Persist result alongside other outputs
    result_path = output_dir / "audio_meta.json"
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    logger.info(f"Audio metadata saved → {result_path}")

    return result


# ── DRY RUN ────────────────────────────────────────────────────────────────────
_DRY_RUN_VTT = """\
WEBVTT

00:00:00.000 --> 00:00:00.280
Inside

00:00:00.280 --> 00:00:00.560
this

00:00:00.560 --> 00:00:00.880
glowing

00:00:00.880 --> 00:00:01.240
cloud,

00:00:01.280 --> 00:00:01.600
thousands

00:00:01.600 --> 00:00:01.960
of

00:00:01.960 --> 00:00:02.320
new

00:00:02.320 --> 00:00:02.640
stars

00:00:02.640 --> 00:00:03.040
are

00:00:03.040 --> 00:00:03.360
being

00:00:03.360 --> 00:00:03.760
born

00:00:03.760 --> 00:00:04.160
right

00:00:04.160 --> 00:00:04.520
now.
"""


def _dry_run(output_dir: Path) -> dict:
    """Write placeholder files for dry-run mode."""
    output_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = output_dir / "narration.mp3"
    vtt_path = output_dir / "narration.vtt"

    # Create a minimal silent MP3 placeholder (1 second, empty)
    mp3_path.write_bytes(b"")
    vtt_path.write_text(_DRY_RUN_VTT, encoding="utf-8")

    result = {
        "mp3_path": str(mp3_path),
        "vtt_path": str(vtt_path),
        "duration_seconds": 20.0,
        "voice": DEFAULT_VOICE,
        "narration": "Dry run — no real audio generated.",
        "dry_run": True,
    }
    result_path = output_dir / "audio_meta.json"
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    logger.info("DRY RUN — wrote placeholder audio files.")
    return result


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Generate TTS audio from narration script.")
    parser.add_argument("--script", default="output/script.json", help="Path to script.json")
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="edge-tts voice name")
    parser.add_argument("--dry-run", action="store_true", help="Skip TTS; write placeholder files")
    args = parser.parse_args()

    output_dir = Path(args.output)

    if args.dry_run:
        result = _dry_run(output_dir)
        print(json.dumps(result, indent=2))
        return

    result = generate_audio(Path(args.script), output_dir, voice=args.voice)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
