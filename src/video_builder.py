"""
video_builder.py
Builds a 1080x1920 vertical YouTube Shorts MP4.

Strategy for Python 3.14 + MoviePy 1.0.3 compatibility:
  1. Pre-render all static Pillow frames into a list of numpy arrays.
  2. Use MoviePy VideoClip (no audio) to write a silent video via write_videofile().
  3. Mix audio (voiceover + optional bg music) with raw ffmpeg subprocess calls.
  4. Mux the silent video + mixed audio into the final MP4 with ffmpeg.

This sidesteps MoviePy's broken FFMPEG_AudioWriter on Python 3.14.
"""

import os
import re
import glob
import random
import logging
import tempfile
import subprocess
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoClip

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------

def parse_srt(srt_path):
    """Parse a standard SRT file → list of {'start', 'end', 'text'} dicts."""
    if not os.path.exists(srt_path):
        logger.warning(f"SRT file not found: {srt_path}")
        return []

    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace("\r\n", "\n").strip()
    blocks = content.split("\n\n")
    subtitles = []

    for block in blocks:
        lines = [l for l in block.strip().split("\n") if l.strip()]
        if len(lines) < 3:
            continue
        time_line = lines[1]
        text = " ".join(lines[2:])
        if " --> " not in time_line:
            continue

        start_str, end_str = time_line.split(" --> ")

        def to_sec(t):
            t = t.strip()
            # handle both comma and period as ms separator
            t = t.replace(",", ".")
            parts = t.split(":")
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + float(s)
            return 0.0

        subtitles.append(
            {"start": to_sec(start_str), "end": to_sec(end_str), "text": text}
        )

    logger.info(f"Parsed {len(subtitles)} subtitle cues from {srt_path}")
    return subtitles


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

def _try_system_fonts(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return None


def get_font(size):
    """Download Montserrat-Bold once, cache in /tmp. Fall back to system fonts."""
    tmp_dir = tempfile.gettempdir()
    font_path = os.path.join(tmp_dir, "Montserrat-Bold.ttf")

    if not os.path.exists(font_path):
        try:
            url = "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat-Bold.ttf"
            logger.info("Downloading Montserrat-Bold font …")
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            with open(font_path, "wb") as f:
                f.write(r.content)
            logger.info(f"Font saved → {font_path}")
        except Exception as e:
            logger.warning(f"Font download failed: {e}")
            font = _try_system_fonts(size)
            if font:
                return font
            logger.warning("No TTF fonts found – using PIL default (will look poor).")
            return ImageFont.load_default()

    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        font = _try_system_fonts(size)
        return font if font else ImageFont.load_default()


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def draw_rounded_rect_alpha(image, box, radius, fill_rgba):
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle(box, radius=radius, fill=fill_rgba)
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def text_outline(draw, text, xy, font, color, outline_color, outline_width=3):
    x, y = xy
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
    draw.text((x, y), text, font=font, fill=color)


def wrap_text(text, font, max_px):
    words, lines, cur = text.split(), [], []
    for word in words:
        cur.append(word)
        w = font.getbbox(" ".join(cur))[2]
        if w > max_px:
            if len(cur) == 1:
                lines.append(word)
                cur = []
            else:
                cur.pop()
                lines.append(" ".join(cur))
                cur = [word]
    if cur:
        lines.append(" ".join(cur))
    return lines


def text_center_x(draw_or_font, text, font, img_width):
    """Return x offset to centre text horizontally."""
    w = font.getbbox(text)[2] - font.getbbox(text)[0]
    return (img_width - w) // 2


# ---------------------------------------------------------------------------
# Static background renderer
# ---------------------------------------------------------------------------

def _fmt_currency(val):
    return f"${int(val):,}"


def _fmt_pct(val):
    return abs(round(val * 100, 1))


def get_active_card_index(t, subtitles):
    # Find all subtitles that started before or at t
    past_subtitles = [s for s in subtitles if s["start"] <= t]
    if not past_subtitles:
        return -1
    
    # Iterate backwards through past subtitles to find the first matching card
    for s in reversed(past_subtitles):
        text = s["text"].lower()
        
        # Reset highlight during intro, outro, or transition phrases
        if any(p in text for p in [
            "break down", "look at three", "what that means", 
            "next move", "right market", "follow for daily"
        ]):
            return -1
            
        if any(w in text for w in ["rent", "rents", "rental", "renter", "renters"]):
            return 1 # Rent Card
        if any(w in text for w in ["price", "home price", "prices", "buying", "negotiat", "seller", "buyer", "cost of home"]):
            return 0 # Price Card
        if any(w in text for w in ["listing", "listings", "inventory", "new listings"]):
            return 2 # Inventory Card
            
    return -1


def pre_render_base_gradient():
    """Build the 1080×1920 base gradient background using Pillow."""
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # --- gradient background ---
    for y in range(H):
        f = y / H
        r = int(10 + 16 * f)
        g = int(10 + 16 * f)
        b = int(10 + 36 * f)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    return img


# ---------------------------------------------------------------------------
# Audio mixing via subprocess ffmpeg
# ---------------------------------------------------------------------------

def _find_ffmpeg():
    """Return path to ffmpeg binary."""
    # imageio_ffmpeg ships a bundled ffmpeg
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.exists(p):
            return p
    except Exception:
        pass
    return "ffmpeg"   # hope it's on PATH


def mix_audio(voiceover_path, music_dir, duration, output_path):
    """
    Mix voiceover + optional background music with ffmpeg subprocess.
    Returns True on success.
    """
    ffmpeg = _find_ffmpeg()

    music_files = []
    if os.path.isdir(music_dir):
        music_files = glob.glob(os.path.join(music_dir, "*.mp3")) + \
                      glob.glob(os.path.join(music_dir, "*.wav"))

    if music_files:
        music = random.choice(music_files)
        logger.info(f"Mixing background music: {os.path.basename(music)}")
        # ffmpeg: loop music, trim to duration, mix at 12% vol, normalise voiceover at 100%
        cmd = [
            ffmpeg, "-y",
            "-i", voiceover_path,
            "-stream_loop", "-1", "-i", music,
            "-filter_complex",
            (
                f"[0:a]apad=pad_dur=1,atrim=0:{duration},volume=1.0[vo];"
                f"[1:a]atrim=0:{duration},volume=0.12[bg];"
                "[vo][bg]amix=inputs=2:duration=first[out]"
            ),
            "-map", "[out]",
            "-t", str(duration),
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ]
    else:
        logger.info("No background music found – using voiceover only.")
        cmd = [
            ffmpeg, "-y",
            "-i", voiceover_path,
            "-filter_complex", f"[0:a]apad=pad_dur=1,atrim=0:{duration}[out]",
            "-map", "[out]",
            "-t", str(duration),
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"ffmpeg audio mix error:\n{result.stderr}")
        return False
    return True


def mux_video_audio(video_path, audio_path, output_path):
    """Combine silent video + audio track with ffmpeg."""
    ffmpeg = _find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"ffmpeg mux error:\n{result.stderr}")
        raise RuntimeError(f"ffmpeg mux failed: {result.stderr[-500:]}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_video(city, state, stats_data, voiceover_path, subtitles_path):
    """
    Build 1080×1920 vertical MP4 for YouTube Shorts.
    Returns the path to the final output file.
    """
    tmp = tempfile.gettempdir()
    silent_path = os.path.join(tmp, "silent_video.mp4")
    mixed_audio_path = os.path.join(tmp, "mixed_audio.aac")
    output_path = os.path.join(tmp, "final_short.mp4")

    # --- 1. Pre-render gradient background ---
    logger.info("Pre-rendering gradient background …")
    bg = pre_render_base_gradient()

    # --- 2. Parse subtitles ---
    logger.info("Parsing SRT subtitles …")
    subtitles = parse_srt(subtitles_path)

    # --- 3. Determine video duration from voiceover ---
    from moviepy.editor import AudioFileClip
    logger.info("Reading voiceover duration …")
    tmp_clip = AudioFileClip(voiceover_path)
    voice_duration = tmp_clip.duration
    tmp_clip.close()
    video_duration = voice_duration + 1.0
    logger.info(f"Voice: {voice_duration:.2f}s  →  Video: {video_duration:.2f}s")

    # --- 4. Subtitle font ---
    sub_font = get_font(46)
    
    # Fonts for dynamic overlays
    tf_city = get_font(68)
    tf_sub  = get_font(36)
    lf = get_font(30)   # label font
    vf = get_font(60)   # value font
    cf = get_font(28)   # change font
    inv_font = get_font(52) # inventory value font
    wf = get_font(28)   # watermark font

    # Pre-render logic for 4 static states (for t >= 1.5s)
    def render_full_state_frame(active_idx):
        frame = bg.copy()
        overlay = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        
        # Titles
        city_text = f"{city.upper()}, {state.upper()}"
        cw = tf_city.getbbox(city_text)[2]
        draw_ov.text(((1080 - cw) // 2, 160), city_text, font=tf_city, fill=(255, 255, 255, 255))
        
        report_text = "REAL ESTATE REPORT"
        rw = tf_sub.getbbox(report_text)[2]
        draw_ov.text(((1080 - rw) // 2, 248), report_text, font=tf_sub, fill=(255, 215, 0, 255))
        
        # Cards
        base_boxes = [
            (80, 380, 1000, 640),
            (80, 690, 1000, 950),
            (80, 1000, 1000, 1260)
        ]
        
        for i in range(3):
            x1, y1, x2, y2 = base_boxes[i]
            
            if active_idx == -1:
                is_active = False
                is_dimmed = False
            elif active_idx == i:
                is_active = True
                is_dimmed = False
            else:
                is_active = False
                is_dimmed = True
                
            if is_active:
                bg_rgba = (255, 255, 255, 40)
                outline_rgba = (255, 215, 0, 220)
                outline_width = 3
            elif is_dimmed:
                bg_rgba = (255, 255, 255, 10)
                outline_rgba = (255, 255, 255, 10)
                outline_width = 1
            else:
                bg_rgba = (255, 255, 255, 20)
                outline_rgba = (255, 255, 255, 20)
                outline_width = 1
                
            draw_ov.rounded_rectangle(
                (x1, y1, x2, y2),
                radius=28,
                fill=bg_rgba,
                outline=outline_rgba,
                width=outline_width
            )
            
            text_mult = 0.4 if is_dimmed else 1.0
            final_alpha = int(255 * text_mult)
            y_center = (y1 + y2) // 2
            
            if i == 0:
                label = "MEDIAN SALE PRICE"
                value_str = _fmt_currency(stats_data["medianPrice"])
                mom_val = stats_data["saleMoM"]
                
                lw = lf.getbbox(label)[2]
                draw_ov.text(((1080 - lw) // 2, y_center - 90), label, font=lf, fill=(190, 190, 190, final_alpha))
                vw = vf.getbbox(value_str)[2]
                draw_ov.text(((1080 - vw) // 2, y_center - 35), value_str, font=vf, fill=(255, 255, 255, final_alpha))
                
                arrow = "▲" if mom_val >= 0 else "▼"
                col_rgb = (76, 175, 80) if mom_val >= 0 else (239, 83, 80)
                col_rgba = (col_rgb[0], col_rgb[1], col_rgb[2], final_alpha)
                ct = f"{arrow} {_fmt_pct(mom_val)}% MoM"
                cw2 = cf.getbbox(ct)[2]
                draw_ov.text(((1080 - cw2) // 2, y_center + 45), ct, font=cf, fill=col_rgba)
                
            elif i == 1:
                label = "MEDIAN MONTHLY RENT"
                value_str = _fmt_currency(stats_data["medianRent"]) + "/mo"
                mom_val = stats_data["rentalMoM"]
                
                lw = lf.getbbox(label)[2]
                draw_ov.text(((1080 - lw) // 2, y_center - 90), label, font=lf, fill=(190, 190, 190, final_alpha))
                vw = vf.getbbox(value_str)[2]
                draw_ov.text(((1080 - vw) // 2, y_center - 35), value_str, font=vf, fill=(255, 255, 255, final_alpha))
                
                arrow = "▲" if mom_val >= 0 else "▼"
                col_rgb = (76, 175, 80) if mom_val >= 0 else (239, 83, 80)
                col_rgba = (col_rgb[0], col_rgb[1], col_rgb[2], final_alpha)
                ct = f"{arrow} {_fmt_pct(mom_val)}% MoM"
                cw2 = cf.getbbox(ct)[2]
                draw_ov.text(((1080 - cw2) // 2, y_center + 45), ct, font=cf, fill=col_rgba)
                
            elif i == 2:
                inv_label = "ACTIVE LISTINGS"
                ilw = lf.getbbox(inv_label)[2]
                draw_ov.text(((1080 - ilw) // 2, y1 + 30), inv_label, font=lf, fill=(190, 190, 190, final_alpha))
                inv_val = f"{int(stats_data['totalListings']):,} total"
                ivw = inv_font.getbbox(inv_val)[2]
                draw_ov.text(((1080 - ivw) // 2, y1 + 78), inv_val, font=inv_font, fill=(255, 255, 255, final_alpha))
                new_txt = f"+{int(stats_data['newListings']):,} new this week"
                nw = cf.getbbox(new_txt)[2]
                draw_ov.text(((1080 - nw) // 2, y1 + 160), new_txt, font=cf, fill=(255, 215, 0, final_alpha))
                
        # Watermark
        wt = "@RealEstatePulse  •  follow for daily updates"
        ww = wf.getbbox(wt)[2]
        draw_ov.text(((1080 - ww) // 2, 1800), wt, font=wf, fill=(130, 130, 130, 130))
        
        frame = Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")
        return frame

    logger.info("Pre-rendering full state frames for performance optimization …")
    state_frames = {
        -1: render_full_state_frame(-1),
        0: render_full_state_frame(0),
        1: render_full_state_frame(1),
        2: render_full_state_frame(2),
    }

    # --- 5. Frame generator ---
    def make_frame(t):
        if t >= 1.5:
            # OPTIMIZED path: retrieve pre-rendered frame for active state
            active_idx = get_active_card_index(t, subtitles)
            frame = state_frames[active_idx].copy()
        else:
            # DYNAMIC path: render fade-in / slide-up animations during entrance phase
            frame = bg.copy()
            overlay = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
            draw_ov = ImageDraw.Draw(overlay)
            
            # Dynamic titles fade-in (over first 0.5s)
            if t < 0.5:
                header_alpha = int((t / 0.5) * 255)
            else:
                header_alpha = 255
                
            city_text = f"{city.upper()}, {state.upper()}"
            cw = tf_city.getbbox(city_text)[2]
            draw_ov.text(((1080 - cw) // 2, 160), city_text, font=tf_city, fill=(255, 255, 255, header_alpha))
            
            report_text = "REAL ESTATE REPORT"
            rw = tf_sub.getbbox(report_text)[2]
            draw_ov.text(((1080 - rw) // 2, 248), report_text, font=tf_sub, fill=(255, 215, 0, header_alpha))
            
            # Dynamic active card tracking
            active_idx = get_active_card_index(t, subtitles)
            
            # Draw dynamic cards
            base_boxes = [
                (80, 380, 1000, 640),
                (80, 690, 1000, 950),
                (80, 1000, 1000, 1260)
            ]
            
            for i in range(3):
                x1, y1, x2, y2 = base_boxes[i]
                
                # Stagger card entrance starts
                start_delay = 0.2 + i * 0.25
                duration = 0.4
                
                if t < start_delay:
                    continue
                    
                y_shift = 0
                card_alpha_factor = 1.0
                
                if t < start_delay + duration:
                    # Slide-up and fade-in entrance
                    progress = (t - start_delay) / duration
                    ease = 1 - (1 - progress) ** 3
                    y_shift = int((1 - ease) * 80)
                    card_alpha_factor = ease
                    is_active = False
                    is_dimmed = False
                else:
                    # Fully entered card states
                    if active_idx == -1:
                        is_active = False
                        is_dimmed = False
                    elif active_idx == i:
                        is_active = True
                        is_dimmed = False
                    else:
                        is_active = False
                        is_dimmed = True
                        
                x1_s, y1_s, x2_s, y2_s = x1, y1 + y_shift, x2, y2 + y_shift
                y_center = (y1_s + y2_s) // 2
                
                # Highlight border and alpha adjustments
                if is_active:
                    bg_rgba = (255, 255, 255, int(40 * card_alpha_factor))
                    outline_rgba = (255, 215, 0, int(220 * card_alpha_factor))
                    outline_width = 3
                elif is_dimmed:
                    bg_rgba = (255, 255, 255, int(10 * card_alpha_factor))
                    outline_rgba = (255, 255, 255, int(10 * card_alpha_factor))
                    outline_width = 1
                else:
                    bg_rgba = (255, 255, 255, int(20 * card_alpha_factor))
                    outline_rgba = (255, 255, 255, int(20 * card_alpha_factor))
                    outline_width = 1
                    
                draw_ov.rounded_rectangle(
                    (x1_s, y1_s, x2_s, y2_s),
                    radius=28,
                    fill=bg_rgba,
                    outline=outline_rgba,
                    width=outline_width
                )
                
                # Text opacity adjustments
                text_mult = 0.4 if is_dimmed else 1.0
                final_alpha = int(255 * card_alpha_factor * text_mult)
                
                if i == 0:
                    label = "MEDIAN SALE PRICE"
                    value_str = _fmt_currency(stats_data["medianPrice"])
                    mom_val = stats_data["saleMoM"]
                    
                    lw = lf.getbbox(label)[2]
                    draw_ov.text(((1080 - lw) // 2, y_center - 90), label, font=lf, fill=(190, 190, 190, final_alpha))
                    
                    vw = vf.getbbox(value_str)[2]
                    draw_ov.text(((1080 - vw) // 2, y_center - 35), value_str, font=vf, fill=(255, 255, 255, final_alpha))
                    
                    arrow = "▲" if mom_val >= 0 else "▼"
                    col_rgb = (76, 175, 80) if mom_val >= 0 else (239, 83, 80)
                    col_rgba = (col_rgb[0], col_rgb[1], col_rgb[2], final_alpha)
                    ct = f"{arrow} {_fmt_pct(mom_val)}% MoM"
                    cw2 = cf.getbbox(ct)[2]
                    draw_ov.text(((1080 - cw2) // 2, y_center + 45), ct, font=cf, fill=col_rgba)
                    
                elif i == 1:
                    label = "MEDIAN MONTHLY RENT"
                    value_str = _fmt_currency(stats_data["medianRent"]) + "/mo"
                    mom_val = stats_data["rentalMoM"]
                    
                    lw = lf.getbbox(label)[2]
                    draw_ov.text(((1080 - lw) // 2, y_center - 90), label, font=lf, fill=(190, 190, 190, final_alpha))
                    
                    vw = vf.getbbox(value_str)[2]
                    draw_ov.text(((1080 - vw) // 2, y_center - 35), value_str, font=vf, fill=(255, 255, 255, final_alpha))
                    
                    arrow = "▲" if mom_val >= 0 else "▼"
                    col_rgb = (76, 175, 80) if mom_val >= 0 else (239, 83, 80)
                    col_rgba = (col_rgb[0], col_rgb[1], col_rgb[2], final_alpha)
                    ct = f"{arrow} {_fmt_pct(mom_val)}% MoM"
                    cw2 = cf.getbbox(ct)[2]
                    draw_ov.text(((1080 - cw2) // 2, y_center + 45), ct, font=cf, fill=col_rgba)
                    
                elif i == 2:
                    inv_label = "ACTIVE LISTINGS"
                    ilw = lf.getbbox(inv_label)[2]
                    draw_ov.text(((1080 - ilw) // 2, y1_s + 30), inv_label, font=lf, fill=(190, 190, 190, final_alpha))
                    
                    inv_val = f"{int(stats_data['totalListings']):,} total"
                    ivw = inv_font.getbbox(inv_val)[2]
                    draw_ov.text(((1080 - ivw) // 2, y1_s + 78), inv_val, font=inv_font, fill=(255, 255, 255, final_alpha))
                    
                    new_txt = f"+{int(stats_data['newListings']):,} new this week"
                    nw = cf.getbbox(new_txt)[2]
                    draw_ov.text(((1080 - nw) // 2, y1_s + 160), new_txt, font=cf, fill=(255, 215, 0, final_alpha))
                    
            # Watermark fade-in (starts at 1.0s, takes 0.5s)
            if t >= 1.0:
                wm_alpha = int(((t - 1.0) / 0.5) * 130)
                wt = "@RealEstatePulse  •  follow for daily updates"
                ww = wf.getbbox(wt)[2]
                draw_ov.text(((1080 - ww) // 2, 1800), wt, font=wf, fill=(130, 130, 130, wm_alpha))
                
            frame = Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")

        # Burn in captions
        active = next(
            (s["text"] for s in subtitles if s["start"] <= t <= s["end"]), ""
        )
        if active:
            d = ImageDraw.Draw(frame)
            lines = wrap_text(active, sub_font, 900)
            lh = sub_font.getbbox("A")[3] + 16
            total_h = len(lines) * lh
            sy = 1530 - total_h // 2
            for i, line in enumerate(lines):
                lw = sub_font.getbbox(line)[2]
                lx = (1080 - lw) // 2
                ly = sy + i * lh
                text_outline(d, line, (lx, ly), sub_font,
                              color=(255, 255, 0),
                              outline_color=(0, 0, 0),
                              outline_width=3)
        return np.array(frame)

    # --- 6. Render silent video with MoviePy ---
    logger.info("Rendering silent video frames with MoviePy …")
    clip = VideoClip(make_frame, duration=video_duration)
    clip.write_videofile(
        silent_path,
        fps=30,
        codec="libx264",
        audio=False,          # ← no audio at all; avoids broken FFMPEG_AudioWriter
        logger="bar",
    )
    clip.close()
    logger.info(f"Silent video saved → {silent_path}")

    # --- 7. Mix audio with ffmpeg ---
    music_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "assets", "music")
    )
    logger.info("Mixing audio with ffmpeg …")
    ok = mix_audio(voiceover_path, music_dir, video_duration, mixed_audio_path)
    if not ok:
        # fall back: just copy voiceover as-is
        logger.warning("Audio mix failed – using raw voiceover.")
        mixed_audio_path = voiceover_path

    # --- 8. Mux video + audio ---
    logger.info("Muxing video + audio …")
    mux_video_audio(silent_path, mixed_audio_path, output_path)

    logger.info(f"✅ Final video → {output_path}")
    return output_path
