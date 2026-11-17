"""Render a clean 16:9 long-form BTS commentary video from licensed photos."""

import logging
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

logger = logging.getLogger("build_longform_video")
WIDTH, HEIGHT, FPS = 1920, 1080, 30


def _portrait_safe_landscape(source: Path, destination: Path) -> None:
    """Use the complete source image over a blurred, darkened copy as a backdrop."""
    with Image.open(source) as original:
        image = original.convert("RGB")
    background = ImageOps.fit(image, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(radius=38))
    background = Image.blend(background, Image.new("RGB", background.size, (12, 10, 20)), 0.28)
    foreground = ImageOps.contain(image, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
    canvas = background.copy()
    canvas.paste(foreground, ((WIDTH - foreground.width) // 2, (HEIGHT - foreground.height) // 2))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, "JPEG", quality=93)


def create_thumbnail(image_path: Path, thumbnail_text: str, output_path: Path) -> Path:
    """Create a 1280x720 photo-led thumbnail; this text is not burned into the video."""
    with Image.open(image_path) as image:
        thumb = ImageOps.fit(image.convert("RGB"), (1280, 720), method=Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", thumb.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle((46, 500, 1234, 678), radius=18, fill=(20, 11, 31, 205))
    try:
        font = ImageFont.truetype("assets/fonts/Montserrat-Bold.ttf", 72)
    except OSError:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 72)
        except OSError:
            font = ImageFont.load_default()
    text = "\n".join(textwrap.wrap(thumbnail_text.strip().upper(), width=24)[:2])
    draw.multiline_text((74, 535), text, font=font, fill=(255, 255, 255, 255), spacing=4, stroke_width=2, stroke_fill=(18, 8, 24, 255))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(thumb.convert("RGBA"), overlay).convert("RGB").save(output_path, "JPEG", quality=94)
    return output_path


def render_longform_video(
    photos: list[dict],
    chapters: list[dict],
    narration: str,
    audio_path: Path,
    audio_duration: float,
    output_path: Path,
) -> Path:
    if len(photos) < len(chapters):
        raise ValueError("Each chapter needs its own licensed visual; not enough source photos were fetched.")
    if not chapters:
        raise ValueError("Long-form script has no chapters to render.")

    image_dir = output_path.parent / "rendered_images"
    normalized = []
    durations = []
    total_words = max(1, len(narration.split()))
    for index, chapter in enumerate(chapters):
        source = Path(photos[index]["local_path"])
        dest = image_dir / f"chapter_{index:02d}.jpg"
        _portrait_safe_landscape(source, dest)
        normalized.append(dest)
        words = len(chapter["narration"].split())
        durations.append(audio_duration * words / total_words)

    concat_path = output_path.parent / "longform_scenes.txt"
    with concat_path.open("w", encoding="utf-8") as scene_list:
        for image, duration in zip(normalized, durations):
            scene_list.write(f"file '{image.resolve().as_posix()}'\n")
            scene_list.write(f"duration {duration:.3f}\n")
        scene_list.write(f"file '{normalized[-1].resolve().as_posix()}'\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path.resolve()),
        "-i", str(audio_path.resolve()), "-map", "0:v:0", "-map", "1:a:0",
        "-t", f"{audio_duration:.3f}", "-r", str(FPS), "-c:v", "libx264",
        "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(output_path.resolve()),
    ]
    logger.info("Rendering 16:9 long-form video with %s licensed chapter images.", len(normalized))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"FFmpeg long-form render failed: {result.stderr[-5000:]}")
    return output_path
