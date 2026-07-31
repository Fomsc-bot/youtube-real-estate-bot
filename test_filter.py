"""Quick test: verify filter string generation & temp-file write for -filter_complex_script."""
import os
import sys
import tempfile
sys.path.insert(0, ".")

from pathlib import Path
from src.build_video import _build_filter_complex

# Simulate 40 karaoke word entries (same as production)
words = [
    {"word": f"WORD{i}", "start_s": i * 0.5, "end_s": i * 0.5 + 0.4}
    for i in range(40)
]

fstr, vlabel, alabel = _build_filter_complex(
    words=words,
    total_duration=21.72,
    hook_text_path=Path("output/hook_text.txt"),
    font_path="assets/fonts/Montserrat-Bold.ttf",
    scenes_meta=[],
    subscribe_badge_exists=False,
    logo_exists=False,
    bgm_exists=False,
)

print(f"Filter string length : {len(fstr):,} chars")
print(f"Video label          : {vlabel}")
print(f"Audio label          : {alabel}")

# Find and print the geq line
geq_lines = [seg for seg in fstr.split(";") if "geq" in seg]
if geq_lines:
    print(f"\ngeq filter (first 200 chars):\n  {geq_lines[0][:200]}")
    # Verify no bad backslash-comma escaping remains
    assert "\\," not in geq_lines[0], "ERROR: stale \\, escaping found in geq filter!"
    print("  -> No stale \\, escaping found. GOOD.")
else:
    print("WARNING: no geq filter found!")

# Verify temp file write works
with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
    f.write(fstr)
    tmp = f.name

size = os.path.getsize(tmp)
print(f"\nTemp file            : {tmp}")
print(f"Temp file size       : {size:,} bytes")
os.unlink(tmp)

print("\n[PASS] filter_complex_script approach is valid.")
