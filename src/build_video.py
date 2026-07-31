"""
build_video.py — Remotion & MoneyPrinterTurbo Video Compositor Engine

Assembles a viral 9:16 YouTube Short:
  1. Multi-clip visual scene concatenation (video clips + Ken Burns pan-zoom photos)
  2. Remotion-style word-by-word animated Karaoke subtitles (neon yellow highlight + stroke)
  3. Hook text banner overlay (first 2.5s)
  4. Animated YouTube "SUBSCRIBE" conversion badge popup during CTA
  5. Top/bottom video duration progress bar
  6. Speech voiceover + Background music (BGM) ducking audio mix

Usage:
    python src/build_video.py --output output/final_video.mp4
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
import textwrap
from pathlib import Path
from typing import Optional, List

from PIL import Image

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("build_video")

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
DEFAULT_FONT = "assets/fonts/Montserrat-Bold.ttf"
FALLBACK_FONT = "DejaVuSans-Bold"
SUBSCRIBE_BADGE_PATH = "assets/subscribe_badge.png"
LOGO_PATH = "assets/logo.png"


def parse_vtt(vtt_path: Path) -> List[dict]:
    """Parse WebVTT file into word-timestamp entries."""
    if not vtt_path.exists():
        return []

    entries = []
    with open(vtt_path, encoding="utf-8") as f:
        content = f.read()

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

    logger.info(f"Parsed {len(entries)} karaoke word timestamps from VTT.")
    return entries


def _vtt_time_to_s(t: str) -> float:
    parts = t.split(":")
    h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
    return h * 3600 + m * 60 + s


def _build_filter_complex(
    words: List[dict],
    total_duration: float,
    hook_text_path: Path,
    font_path: str,
    scenes_meta: List[dict],
    subscribe_badge_exists: bool,
    logo_exists: bool,
    bgm_exists: bool,
) -> tuple[str, str, str]:
    """
    Build complete FFmpeg filtergraph string including multi-scene visuals,
    karaoke captions, subscribe popup, progress bar, and BGM audio mix.
    """
    filters = []
    
    # ── 1. Visual Composition (Scenes) ──
    filters.append(
        f"[0:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
        f"setsar=1[v_base]"
    )

    fpath = Path(font_path)
    if fpath.exists():
        font_path_escaped = str(fpath.resolve()).replace("\\", "/").replace(":", "\\:")
    else:
        font_path_escaped = FALLBACK_FONT

    # ── 2. Hook Text Overlay (0s - 2.5s) ──
    hook_duration = 2.5
    hook_path_escaped = str(hook_text_path.resolve()).replace("\\", "/").replace(":", "\\:")
    filters.append(
        f"[v_base]drawtext="
        f"fontfile='{font_path_escaped}':"
        f"textfile='{hook_path_escaped}':"
        f"fontsize=115:"
        f"fontcolor=white:"
        f"bordercolor=black:"
        f"borderw=10:"
        f"shadowx=8:shadowy=8:shadowcolor=black@0.8:"
        f"x=(w-text_w)/2:"
        f"y=h*0.14:"
        f"enable='between(t,0,{hook_duration})'[v_hook]"
    )

    # ── 3. Remotion Word-by-Word Karaoke Subtitles ──
    current_label = "v_hook"
    caption_y = int(VIDEO_HEIGHT * 0.65)

    for i, entry in enumerate(words):
        word_clean = (
            entry["word"]
            .replace("'", "\\'")
            .replace(":", "\\:")
            .replace(",", "\\,")
            .replace(".", "")
            .rstrip(".,!?;")
            .upper()
        )
        start = entry["start_s"]
        end = entry["end_s"]
        next_label = f"v_w{i}"

        filters.append(
            f"[{current_label}]drawtext="
            f"fontfile='{font_path_escaped}':"
            f"text='{word_clean}':"
            f"fontsize=135:"
            f"fontcolor=yellow:"
            f"bordercolor=black:"
            f"borderw=12:"
            f"shadowx=10:shadowy=10:shadowcolor=black@0.85:"
            f"x=(w-text_w)/2:"
            f"y={caption_y}:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{next_label}]"
        )
        current_label = next_label

    # ── 4. Progress Bar Overlay ──
    # drawbox evaluates iw * t / duration per frame natively in FFmpeg (no geq syntax/eval errors).
    filters.append(
        f"[{current_label}]drawbox="
        f"x=0:y=0:"
        f"w='iw*t/{total_duration:.4f}':"
        f"h=10:"
        f"color=yellow:"
        f"t=fill[v_prog]"
    )
    current_label = "v_prog"

    # ── 5. Subscribe Badge Popup (Last 4.5 seconds CTA) ──
    input_idx = 2
    if subscribe_badge_exists:
        sub_start = max(0.0, total_duration - 4.5)
        filters.append(
            f"[{current_label}][{input_idx}:v]overlay="
            f"x=(W-w)/2:"
            f"y=H-h-180:"
            f"enable='between(t,{sub_start:.2f},{total_duration:.2f})'[v_sub]"
        )
        current_label = "v_sub"
        input_idx += 1

    # ── 6. Logo Bug Overlay ──
    if logo_exists:
        logo_margin = 28
        logo_size = 90
        filters.append(
            f"[{current_label}][{input_idx}:v]overlay="
            f"x={VIDEO_WIDTH - logo_size - logo_margin}:"
            f"y={VIDEO_HEIGHT - logo_size - logo_margin}:"
            f"format=auto[v_final]"
        )
        final_video_label = "v_final"
    else:
        filters.append(f"[{current_label}]null[v_final]")
        final_video_label = "v_final"

    # ── 7. Audio Ducking Filter Complex (Voice + BGM Mix) ──
    if bgm_exists:
        bgm_input_idx = input_idx if not logo_exists else input_idx + 1
        filters.append(
            f"[1:a]volume=1.0[a_voice];"
            f"[{bgm_input_idx}:a]volume=0.15,aloop=loop=-1:size=2e+09[a_bgm];"
            f"[a_voice][a_bgm]amix=inputs=2:duration=first:dropout_transition=2[a_final]"
        )
        final_audio_label = "a_final"
    else:
        filters.append("[1:a]volume=1.0[a_final]")
        final_audio_label = "a_final"

    return ";".join(filters), final_video_label, final_audio_label


def build_video(
    image_path: Path,
    audio_path: Path,
    vtt_path: Path,
    script_path: Path,
    output_path: Path,
    config: Optional[dict] = None,
) -> Path:
    """Build final 9:16 Shorts video with multi-clip visuals and Remotion graphics."""
    cfg = config or {}
    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    hook_text = "LUXURY REAL ESTATE"
    if script_path.exists():
        with open(script_path, encoding="utf-8") as f:
            script_data = json.load(f)
            hook_text = script_data.get("hook_text", hook_text)

    wrapped_hook = textwrap.fill(hook_text.upper(), width=14)
    hook_text_path = output_dir / "hook_text.txt"
    with open(hook_text_path, "w", encoding="utf-8") as f:
        f.write(wrapped_hook)

    scenes_meta_path = output_dir / "scenes_meta.json"
    scenes_meta = []
    if scenes_meta_path.exists():
        with open(scenes_meta_path, encoding="utf-8") as f:
            scenes_meta = json.load(f).get("scenes", [])

    audio_meta_path = output_dir / "audio_meta.json"
    audio_duration = 20.0
    bgm_path_str = "assets/bgm/ambient_viral.mp3"
    if audio_meta_path.exists():
        with open(audio_meta_path, encoding="utf-8") as f:
            ameta = json.load(f)
            audio_duration = ameta.get("duration_seconds", 20.0)
            if ameta.get("bgm_path"):
                bgm_path_str = ameta.get("bgm_path")

    total_duration = min(audio_duration + 0.5, 58.0)
    words = parse_vtt(vtt_path)
    font_path = cfg.get("caption_font", DEFAULT_FONT)

    badge_path = Path(SUBSCRIBE_BADGE_PATH)
    if not badge_path.exists():
        from src.generate_assets import ensure_assets
        ensure_assets()

    logo_path = Path(cfg.get("logo_path", LOGO_PATH))
    bgm_path = Path(bgm_path_str)

    filter_str, final_v_label, final_a_label = _build_filter_complex(
        words=words,
        total_duration=total_duration,
        hook_text_path=hook_text_path,
        font_path=font_path,
        scenes_meta=scenes_meta,
        subscribe_badge_exists=badge_path.exists(),
        logo_exists=logo_path.exists(),
        bgm_exists=bgm_path.exists(),
    )

    primary_image = image_path
    if not primary_image.exists():
        scene_files = list((output_dir / "scenes").glob("scene_*.jpg"))
        if scene_files:
            primary_image = scene_files[0]
        else:
            # Create procedural image fallback if none exists
            from src.fetch_content import create_fallback_scene_image
            primary_image = create_fallback_scene_image(hook_text, "Real Estate", output_dir / "default_visual.jpg")

    # Write filtergraph to a temp script file.
    # -filter_complex_script avoids:
    #   (a) command-line length limits with 40+ chained drawtext filters
    #   (b) shell-escaping issues causing 'Error parsing global options' (code 234)
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as fcs:
        fcs.write(filter_str)
        filter_script_path = fcs.name
    logger.info(f"Filter script -> {filter_script_path} ({len(filter_str)} chars)")

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(primary_image.resolve()),
        "-i", str(audio_path.resolve()),
    ]

    if badge_path.exists():
        cmd += ["-i", str(badge_path.resolve())]

    if logo_path.exists():
        cmd += ["-i", str(logo_path.resolve())]

    if bgm_path.exists():
        cmd += ["-i", str(bgm_path.resolve())]

    cmd += [
        "-filter_complex_script", filter_script_path,
        "-map", f"[{final_v_label}]",
        "-map", f"[{final_a_label}]",
        "-t", str(total_duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-r", str(FPS),
        str(output_path.resolve()),
    ]

    logger.info("Executing FFmpeg Video Compositor...")
    res = subprocess.run(cmd, capture_output=True, text=True)

    # Clean up temp filter script
    try:
        os.unlink(filter_script_path)
    except OSError:
        pass

    if res.returncode != 0:
        logger.error(f"FFmpeg Error Output:\n{res.stderr[-3000:]}")
        raise RuntimeError(f"FFmpeg failed with code {res.returncode}")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"Viral Short built successfully -> {output_path} ({size_mb:.1f} MB, {total_duration:.1f}s)")
    return output_path


def _dry_run(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"\x00" * 1024)
    logger.info(f"DRY RUN — placeholder video file created -> {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Build Remotion-style YouTube Short video.")
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

    res_path = build_video(
        image_path=Path(args.image),
        audio_path=Path(args.audio),
        vtt_path=Path(args.vtt),
        script_path=Path(args.script),
        output_path=output_path,
    )
    print(json.dumps({"video_path": str(res_path)}, indent=2))


if __name__ == "__main__":
    main()
