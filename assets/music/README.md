# Royalty-Free Background Music Folder

Place your royalty-free background music `.mp3` or `.wav` files directly in this folder.

## Music Selection Logic

The video builder (`src/build_video.py`) automatically scans this folder during execution:
- It uses the first audio file in alphabetical order, which makes runs reproducible.
- It loops that track to cover the voiceover and mixes it at 10% volume under the narration.
- **Fail-safe**: If this folder is empty, the bot will compile the video with ONLY the voiceover, and will not crash.

Only add tracks that you have permission to use on YouTube. A track from YouTube Audio Library is a good option; follow any attribution requirements shown for that track.

## Recommended Free Sources

You can find excellent royalty-free background music (non-copyrighted tracks) at:
1. **YouTube Audio Library**: Access via your YouTube Studio panel. Great filter options.
2. **Pixabay Music**: Search for "Lo-Fi", "Hip Hop", or "Upbeat Real Estate".
3. **Free Music Archive (FMA)**: Download CC-licensed instrumental tracks.
4. **Bensound**: Choose from their free license tier (requires attribution in the video description).
