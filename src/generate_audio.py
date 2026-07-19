"""
generate_audio.py — Step 3 of The Universe pipeline.

Converts the narration script to speech using gTTS (Google Text-to-Speech).
Outputs an MP3 audio file and an approximate WebVTT caption file 
since gTTS does not provide word-level timestamps out of the box.

Voice: Default gTTS (en)
Usage:
    python src/generate_audio.py --script output/script.json
    python src/generate_audio.py --script output/script.json --output output/
    python src/generate_audio.py --dry-run
"""

import argparse
import json
import logging
import subprocess
from pathlib import Path

from gtts import gTTS

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("generate_audio")

# ── Config ─────────────────────────────────────────────────────────────────────
DEFAULT_VOICE = "en"  # For gTTS, this is the language code


# ── Core generation ────────────────────────────────────────────────────────────
def _format_vtt_time(seconds: float) -> str:
    """Format seconds into VTT time string (HH:MM:SS.mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

def _generate_vtt_approx(text: str, duration: float, vtt_path: Path):
    """Generate approximate VTT subtitle file based on word count and total duration."""
    words = text.split()
    if not words:
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
        return
    
    word_duration = duration / len(words)
    vtt_content = ["WEBVTT", ""]
    
    current_time = 0.0
    for word in words:
        start_time = _format_vtt_time(current_time)
        current_time += word_duration
        end_time = _format_vtt_time(current_time)
        vtt_content.append(f"{start_time} --> {end_time}")
        vtt_content.append(word)
        vtt_content.append("")
        
    with open(vtt_path, "w", encoding="utf-8") as vtt_file:
        vtt_file.write("\n".join(vtt_content))

def _generate_tts(
    text: str,
    mp3_path: Path,
    voice: str = DEFAULT_VOICE,
) -> None:
    """Run gTTS and produce MP3."""
    mp3_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Generating TTS with gTTS (lang={voice}) ...")
    
    tts = gTTS(text=text, lang=voice, slow=False)
    tts.save(str(mp3_path))

    logger.info(f"Audio saved → {mp3_path}")


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

    _generate_tts(narration, mp3_path, voice=voice)

    duration = _get_audio_duration(mp3_path)
    logger.info(f"Audio duration: {duration:.2f}s")
    
    _generate_vtt_approx(narration, duration, vtt_path)
    logger.info(f"Approximate word-level VTT saved → {vtt_path}")

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
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="gTTS language code")
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
