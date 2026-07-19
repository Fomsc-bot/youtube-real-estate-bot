"""
build_video.py — Step 4 of The Universe pipeline.

Assembles the final 9:16 YouTube Short using FFmpeg:
  1. Crops/pads the APOD image to 1080×1920 vertical (with blurred background fill)
  2. Adds the narration audio track
  3. Burns in animated word-by-word highlighted captions from VTT timestamps
  4. Overlays the channel logo bug (bottom-right, semi-transparent)
  5. Adds bold hook text overlay for the first 2.5 seconds
  6. Outputs a Shorts-compliant H.264/AAC MP4

Usage:
    python src/build_video.py \\
        --image output/apod_image.jpg \\
        --audio output/narration.mp3 \\
        --vtt   output/narration.vtt \\
        --script output/script.json \\
        --output output/final_video.mp4

    python src/build_video.py --dry-run
"""

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PIL import Image

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("build_video")

# ── Constants ──────────────────────────────────────────────────────────────────
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
DEFAULT_FONT = "assets/fonts/Montserrat-Bold.ttf"
FALLBACK_FONT = "DejaVuSans-Bold"   # System font fallback on Ubuntu CI
LOGO_PATH = "assets/logo.png"


# ── VTT Parsing ────────────────────────────────────────────────────────────────
def parse_vtt(vtt_path: Path) -> list[dict]:
    """
    Parse WebVTT file into list of word-timestamp dicts.
    Each entry: {word, start_s, end_s}
    """
    entries = []
    with open(vtt_path, encoding="utf-8") as f:
        content = f.read()

    # Find all cue blocks: timestamp --> timestamp\nword
    pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\s*\n(.+?)(?=\n\n|\Z)",
        re.DOTALL,
    )
    for m in pattern.finditer(content):
        start_s = _vtt_time_to_s(m.group(1))
        end_s = _vtt_time_to_s(m.group(2))
        word = m.group(3).strip()
        if word:
            entries.append({"word": word, "start_s": start_s, "end_s": end_s})

    logger.info(f"Parsed {len(entries)} word timestamps from VTT")
    return entries


def _vtt_time_to_s(t: str) -> float:
    """Convert HH:MM:SS.mmm to seconds float."""
    parts = t.split(":")
    h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
    return h * 3600 + m * 60 + s


# ── Image preparation ──────────────────────────────────────────────────────────
def prepare_image(image_path: Path, output_dir: Path) -> Path:
    """
    Prepare the APOD image for vertical 9:16 format using Pillow for initial
    resize, then let FFmpeg handle the blurred-background fill.
    Returns path to the prepared image (same as input if already fine).
    """
    img = Image.open(image_path)
    w, h = img.size
    logger.info(f"Source image: {w}×{h} pixels, mode={img.mode}")

    # Convert RGBA/P to RGB for FFmpeg compatibility
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
        converted_path = output_dir / "apod_converted.jpg"
        img.save(converted_path, "JPEG", quality=95)
        logger.info(f"Converted image mode to RGB → {converted_path}")
        return converted_path

    return image_path


# ── FFmpeg filter graph ────────────────────────────────────────────────────────
def _build_filter_complex(
    words: list[dict],
    audio_duration: float,
    hook_text: str,
    font_path: str,
    logo_exists: bool,
) -> str:
    """
    Build the FFmpeg filtergraph string.
    Layout:
      - [0:v] = APOD image (scaled + blurred for background)
      - [1:v] = logo PNG (if exists)
      - word captions burned in via drawtext
    """
    filters = []

    # ── 1. Background: blurred stretched version of image ──────────────────────
    filters.append(
        f"[0:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
        f"boxblur=20:1[bg]"
    )

    # ── 2. Foreground: scale image to fit within 9:16, preserve aspect ratio ──
    filters.append(
        f"[0:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease[fg_raw]"
    )

    # ── 3. Overlay foreground on blurred background ───────────────────────────
    filters.append(
        f"[bg][fg_raw]overlay=(W-w)/2:(H-h)/2[composited]"
    )

    # Resolve font path
    font_path_escaped = font_path.replace("\\", "/").replace(":", "\\:")
    if not Path(font_path).exists():
        font_path_escaped = FALLBACK_FONT
        logger.warning(f"Custom font not found at {font_path}, using system font: {FALLBACK_FONT}")

    # ── 4. Hook text overlay (first hook_duration seconds) ───────────────────
    hook_clean = hook_text.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
    hook_duration = 2.5
    filters.append(
        f"[composited]drawtext="
        f"fontfile={font_path_escaped}:"
        f"text='{hook_clean}':"
        f"fontsize=72:"
        f"fontcolor=white:"
        f"bordercolor=black:"
        f"borderw=4:"
        f"x=(w-text_w)/2:"
        f"y=h*0.12:"
        f"enable='between(t,0,{hook_duration})':"
        f"box=1:"
        f"boxcolor=black@0.45:"
        f"boxborderw=20[with_hook]"
    )

    # ── 5. Word-by-word animated captions ────────────────────────────────────
    base_layer = "with_hook"
    caption_y = int(VIDEO_HEIGHT * 0.72)
    out_label = base_layer

    for i, entry in enumerate(words):
        word_clean = entry["word"].replace("'", "\\'").replace(":", "\\:").replace(",", "\\,").replace(".", "").rstrip(".,!?;")
        start = entry["start_s"]
        end = entry["end_s"]
        label_in = out_label
        label_out = f"w{i}"

        # Highlighted word (yellow + slightly larger)
        filters.append(
            f"[{label_in}]drawtext="
            f"fontfile={font_path_escaped}:"
            f"text='{word_clean}':"
            f"fontsize=60:"
            f"fontcolor=yellow:"
            f"bordercolor=black:"
            f"borderw=4:"
            f"x=(w-text_w)/2:"
            f"y={caption_y}:"
            f"enable='between(t,{start:.3f},{end:.3f})':"
            f"box=1:"
            f"boxcolor=black@0.55:"
            f"boxborderw=14[{label_out}]"
        )
        out_label = label_out

    # ── 6. Logo overlay ────────────────────────────────────────────────────────
    if logo_exists:
        logo_margin = 28
        logo_size = 90
        filters.append(
            f"[{out_label}][2:v]overlay="
            f"x={VIDEO_WIDTH - logo_size - logo_margin}:"
            f"y={VIDEO_HEIGHT - logo_size - logo_margin}:"
            f"format=auto[final]"
        )
        final_label = "final"
    else:
        # Rename last label to 'final' for output
        filters[-1] = filters[-1].replace(f"[{out_label}]", f"[{out_label}]").rstrip("]") + \
                       "]" if not filters[-1].endswith("[final]") else filters[-1]
        # Simple alias
        filters.append(f"[{out_label}]null[final]")
        final_label = "final"

    return ";".join(filters), final_label


def _run_ffmpeg(cmd: list[str]) -> None:
    """Run an FFmpeg command and log output. Raise on non-zero exit."""
    logger.info("FFmpeg command: " + " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"FFmpeg STDERR:\n{result.stderr[-3000:]}")
        raise RuntimeError(f"FFmpeg failed with code {result.returncode}")
    logger.info("FFmpeg completed successfully.")


# ── Logo preparation ───────────────────────────────────────────────────────────
def _prepare_logo(logo_path: str, output_dir: Path, size: int = 90, opacity: float = 0.65) -> Optional[Path]:
    """Resize and set opacity on the logo; return path or None if not found."""
    lp = Path(logo_path)
    if not lp.exists():
        logger.warning(f"Logo not found at {lp} — skipping logo overlay.")
        return None

    out = output_dir / "logo_prepared.png"
    img = Image.open(lp).convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)

    # Apply opacity to alpha channel
    r, g, b, a = img.split()
    a = a.point(lambda x: int(x * opacity))
    img.putalpha(a)

    img.save(out, "PNG")
    logger.info(f"Logo prepared → {out} ({size}×{size}, opacity={opacity})")
    return out


# ── Main builder ───────────────────────────────────────────────────────────────
def build_video(
    image_path: Path,
    audio_path: Path,
    vtt_path: Path,
    script_path: Path,
    output_path: Path,
    config: Optional[dict] = None,
) -> Path:
    """
    Build the final 9:16 MP4 Short.
    Returns the path to the output video.
    """
    cfg = config or {}
    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load script metadata
    with open(script_path) as f:
        script_data = json.load(f)
    hook_text = script_data.get("hook_text", "Today in Space")

    # Prepare image
    prepared_image = prepare_image(image_path, output_dir)

    # Parse VTT captions
    words = parse_vtt(vtt_path) if vtt_path.exists() else []

    # Prepare logo
    logo_prepared = _prepare_logo(
        cfg.get("logo_path", LOGO_PATH),
        output_dir,
        size=cfg.get("logo_size", 90),
        opacity=cfg.get("logo_opacity", 0.65),
    )

    # Get audio duration for video length
    audio_meta_path = output_dir / "audio_meta.json"
    audio_duration = 25.0  # default
    if audio_meta_path.exists():
        with open(audio_meta_path) as f:
            meta = json.load(f)
            audio_duration = meta.get("duration_seconds", 25.0)

    # Add 0.5s tail after audio ends
    video_duration = min(audio_duration + 0.5, 58.0)

    font_path = cfg.get("caption_font", DEFAULT_FONT)

    # Build filter complex
    filter_str, final_label = _build_filter_complex(
        words=words,
        audio_duration=audio_duration,
        hook_text=hook_text,
        font_path=font_path,
        logo_exists=logo_prepared is not None,
    )

    # Build FFmpeg command
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(prepared_image),       # [0:v] input image (looped)
        "-i", str(audio_path),                          # [1:a] audio
    ]

    if logo_prepared:
        cmd += ["-i", str(logo_prepared)]               # [2:v] logo

    cmd += [
        "-filter_complex", filter_str,
        "-map", f"[{final_label}]",
        "-map", "1:a",
        "-t", str(video_duration),
        "-c:v", "libx264",
        "-preset", cfg.get("video_preset", "fast"),
        "-crf", str(cfg.get("crf", 23)),
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-r", str(FPS),
        str(output_path),
    ]

    _run_ffmpeg(cmd)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"Video built → {output_path} ({size_mb:.1f} MB, {video_duration:.1f}s)")
    return output_path


# ── DRY RUN ────────────────────────────────────────────────────────────────────
def _dry_run(output_path: Path) -> Path:
    """Create a minimal placeholder MP4 for pipeline testing."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Create a 1-second black Shorts video
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=black:{VIDEO_WIDTH}x{VIDEO_HEIGHT}:d=1",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "1",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        logger.info(f"DRY RUN — placeholder video created → {output_path}")
    except Exception as e:
        logger.warning(f"Could not create placeholder video: {e}. Writing empty file.")
        output_path.write_bytes(b"")
    return output_path


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Build 9:16 Short video from APOD image + audio.")
    parser.add_argument("--image", default="output/apod_image.jpg")
    parser.add_argument("--audio", default="output/narration.mp3")
    parser.add_argument("--vtt", default="output/narration.vtt")
    parser.add_argument("--script", default="output/script.json")
    parser.add_argument("--output", default="output/final_video.mp4")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output_path = Path(args.output)

    if args.dry_run:
        _dry_run(output_path)
        print(json.dumps({"video_path": str(output_path), "dry_run": True}, indent=2))
        return

    result_path = build_video(
        image_path=Path(args.image),
        audio_path=Path(args.audio),
        vtt_path=Path(args.vtt),
        script_path=Path(args.script),
        output_path=output_path,
    )
    print(json.dumps({"video_path": str(result_path)}, indent=2))


if __name__ == "__main__":
    main()
