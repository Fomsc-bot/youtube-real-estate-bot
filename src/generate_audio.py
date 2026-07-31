"""
generate_audio.py — Step 3 of YouTube Shorts Pipeline

Converts narration script to high-clarity speech using gTTS.
Builds word-level WebVTT timestamps for Remotion karaoke subtitles.
Prepares background music (BGM) track for audio ducking mix in build_video.py.

Usage:
    python src/generate_audio.py --script output/script.json
    python src/generate_audio.py --dry-run
"""

import argparse
import json
import logging
import math
import subprocess
from pathlib import Path
from typing import Optional

from gtts import gTTS

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("generate_audio")

DEFAULT_VOICE = "en"


def _format_vtt_time(seconds: float) -> str:
    """Format seconds into VTT time string (HH:MM:SS.mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _generate_vtt_timestamps(text: str, duration: float, vtt_path: Path):
    """Generate precise WebVTT timestamps for each word to drive karaoke subtitles."""
    words = text.split()
    if not words:
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
        return

    # Calculate word durations (weight longer words slightly higher)
    char_counts = [max(1, len(w)) for w in words]
    total_chars = sum(char_counts)
    
    vtt_content = ["WEBVTT", ""]
    current_time = 0.1  # start offset
    
    for word, char_len in zip(words, char_counts):
        w_duration = (char_len / total_chars) * (duration - 0.2)
        w_duration = max(0.20, w_duration)  # min word display 200ms
        
        start_t = _format_vtt_time(current_time)
        current_time += w_duration
        end_t = _format_vtt_time(current_time)
        
        vtt_content.append(f"{start_t} --> {end_t}")
        vtt_content.append(word)
        vtt_content.append("")

    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(vtt_content))

    logger.info(f"Generated WebVTT karaoke timestamps -> {vtt_path}")


def _generate_tts(text: str, mp3_path: Path, voice: str = DEFAULT_VOICE) -> None:
    """Run gTTS to produce narration speech MP3."""
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Generating TTS audio with gTTS (lang={voice})...")
    tts = gTTS(text=text, lang=voice, slow=False)
    tts.save(str(mp3_path))
    logger.info(f"TTS Audio saved -> {mp3_path}")


def _get_audio_duration(mp3_path: Path) -> float:
    """Use ffprobe or fallback to estimate audio duration in seconds."""
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
        logger.warning(f"ffprobe duration check warning: {e}")
        
    # File size estimate fallback for 128kbps MP3 if ffprobe unavailable
    try:
        bytes_count = mp3_path.stat().st_size
        return max(5.0, round(bytes_count / 16000.0, 2))
    except Exception:
        return 20.0


def generate_audio(
    script_path: Path,
    output_dir: Path,
    voice: str = DEFAULT_VOICE,
    bgm_path: Optional[Path] = None,
) -> dict:
    """
    Generate audio narration, WebVTT karaoke timestamps, and locate BGM audio.
    """
    with open(script_path, encoding="utf-8") as f:
        script_data = json.load(f)

    narration = script_data.get("narration", "")
    if not narration:
        raise ValueError(f"No 'narration' text found in {script_path}")

    mp3_path = output_dir / "narration.mp3"
    vtt_path = output_dir / "narration.vtt"

    _generate_tts(narration, mp3_path, voice=voice)
    duration = _get_audio_duration(mp3_path)
    logger.info(f"Speech audio duration: {duration:.2f}s")

    _generate_vtt_timestamps(narration, duration, vtt_path)

    # Locate ambient background music
    if not bgm_path:
        bgm_path = Path("assets/bgm/ambient_viral.mp3")

    result = {
        "mp3_path": str(mp3_path),
        "vtt_path": str(vtt_path),
        "bgm_path": str(bgm_path) if bgm_path.exists() else None,
        "duration_seconds": round(duration, 3),
        "voice": voice,
        "narration": narration,
    }

    result_path = output_dir / "audio_meta.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    logger.info(f"Audio metadata saved -> {result_path}")
    return result


# ── DRY RUN ────────────────────────────────────────────────────────────────────
_DRY_RUN_VTT = """WEBVTT

00:00:00.100 --> 00:00:00.500
Inside

00:00:00.500 --> 00:00:00.800
this

00:00:00.800 --> 00:00:01.300
$100

00:00:01.300 --> 00:00:01.800
Million

00:00:01.800 --> 00:00:02.300
Mega

00:00:02.300 --> 00:00:02.800
Mansion
"""


def _dry_run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = output_dir / "narration.mp3"
    vtt_path = output_dir / "narration.vtt"
    bgm_path = Path("assets/bgm/ambient_viral.mp3")

    mp3_path.write_bytes(b"")
    vtt_path.write_text(_DRY_RUN_VTT, encoding="utf-8")

    result = {
        "mp3_path": str(mp3_path),
        "vtt_path": str(vtt_path),
        "bgm_path": str(bgm_path) if bgm_path.exists() else None,
        "duration_seconds": 22.0,
        "voice": DEFAULT_VOICE,
        "narration": "Dry run narration audio.",
        "dry_run": True,
    }
    result_path = output_dir / "audio_meta.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    logger.info("DRY RUN audio files written.")
    return result


def main():
    parser = argparse.ArgumentParser(description="Generate TTS audio & karaoke WebVTT timestamps.")
    parser.add_argument("--script", default="output/script.json", help="Path to script.json")
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="gTTS language code")
    parser.add_argument("--dry-run", action="store_true", help="Skip TTS API; write placeholders")
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
