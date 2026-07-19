# Royalty-Free Background Music Folder

Place your royalty-free background music `.mp3` or `.wav` files directly in this folder.

## Music Selection Logic

The video builder module (`src/video_builder.py`) automatically scans this folder during execution:
- If multiple audio files are present, it randomly selects one track for the video background.
- It loops the background music track to cover the full duration of the voiceover.
- It mixes the background track at low volume (12% to 15%) so it doesn't overpower the voiceover.
- **Fail-safe**: If this folder is empty, the bot will compile the video with ONLY the voiceover, and will not crash.

## Recommended Free Sources

You can find excellent royalty-free background music (non-copyrighted tracks) at:
1. **YouTube Audio Library**: Access via your YouTube Studio panel. Great filter options.
2. **Pixabay Music**: Search for "Lo-Fi", "Hip Hop", or "Upbeat Real Estate".
3. **Free Music Archive (FMA)**: Download CC-licensed instrumental tracks.
4. **Bensound**: Choose from their free license tier (requires attribution in the video description).
