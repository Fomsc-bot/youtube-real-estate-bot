"""
generate_assets.py — Helper to generate default overlay graphics and audio assets.
Generates assets/subscribe_badge.png and assets/bgm/ambient_viral.mp3 if absent.
"""

import math
import os
import struct
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def create_subscribe_badge(output_path: Path):
    """Generate a clean YouTube SUBSCRIBE badge image with red background & bell icon."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 480, 120
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw rounded rectangle background (YouTube Red: #FF0000)
    rect_box = [10, 10, width - 10, height - 10]
    draw.rounded_rectangle(rect_box, radius=24, fill=(255, 0, 0, 240), outline=(255, 255, 255, 255), width=3)

    # Add text "SUBSCRIBE 🔔"
    try:
        font = ImageFont.truetype("arial.ttf", 44)
    except IOError:
        font = ImageFont.load_default()

    draw.text((width // 2, height // 2), "SUBSCRIBE", fill=(255, 255, 255), font=font, anchor="mm")
    img.save(output_path, "PNG")
    print(f"Generated subscribe badge -> {output_path}")


def create_ambient_bgm(output_path: Path):
    """Generate a soft ambient background music loop (MP3/WAV) using math synth."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wav_path = output_path.with_suffix(".wav")
    
    sample_rate = 44100
    duration = 30.0  # 30 seconds
    num_samples = int(sample_rate * duration)
    
    with wave.open(str(wav_path), "w") as wav_file:
        wav_file.setnchannels(2)  # Stereo
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        
        # Soft chord pads (A minor / C major chill vibes)
        freqs = [220.0, 261.63, 329.63, 392.00]  # A, C, E, G
        frames = bytearray()
        
        for i in range(num_samples):
            t = float(i) / sample_rate
            # LFO modulation
            lfo = 0.5 + 0.5 * math.sin(2 * math.pi * 0.2 * t)
            sample_val = 0
            for f in freqs:
                sample_val += math.sin(2 * math.pi * f * t)
            
            sample_val = sample_val / len(freqs) * 0.15 * lfo  # keep volume low
            int_val = int(sample_val * 32767)
            frames.extend(struct.pack("<h", int_val))
            frames.extend(struct.pack("<h", int_val))
            
        wav_file.writeframes(frames)

    # If ffmpeg is available, convert to mp3, else keep wav/copy
    try:
        import subprocess
        subprocess.run(["ffmpeg", "-y", "-i", str(wav_path), "-b:a", "128k", str(output_path)],
                       capture_output=True, check=True)
        os.remove(wav_path)
    except Exception:
        if wav_path.exists() and not output_path.exists():
            wav_path.rename(output_path)
            
    print(f"Generated ambient BGM audio -> {output_path}")


def ensure_assets():
    assets_dir = Path("assets")
    badge_path = assets_dir / "subscribe_badge.png"
    bgm_path = assets_dir / "bgm" / "ambient_viral.mp3"
    
    if not badge_path.exists():
        create_subscribe_badge(badge_path)
    if not bgm_path.exists():
        create_ambient_bgm(bgm_path)


if __name__ == "__main__":
    ensure_assets()
