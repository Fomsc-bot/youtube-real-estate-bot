"""Generate the default subscribe overlay graphic when it is missing."""

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


def ensure_assets():
    badge_path = Path("assets/subscribe_badge.png")
    if not badge_path.exists():
        create_subscribe_badge(badge_path)


if __name__ == "__main__":
    ensure_assets()
