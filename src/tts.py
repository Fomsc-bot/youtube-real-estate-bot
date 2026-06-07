import os
import asyncio
import logging
import tempfile
import edge_tts

logger = logging.getLogger(__name__)

async def generate_tts(script: str) -> tuple[str, str]:
    """
    Convert script to speech using edge-tts.
    Voice: en-US-AriaNeural
    Rate: +5%
    Saves:
      - Voiceover to cross-platform /tmp/voiceover.mp3
      - Subtitles to cross-platform /tmp/subtitles.srt (word-level timestamps)
    Returns: (voiceover_path, subtitles_path)
    """
    voice = "en-US-AriaNeural"
    rate = "+5%"
    
    # Resolve cross-platform temp directories
    tmp_dir = "/tmp" if os.path.exists("/tmp") and os.access("/tmp", os.W_OK) else tempfile.gettempdir()
    voiceover_path = os.path.join(tmp_dir, "voiceover.mp3")
    subtitles_path = os.path.join(tmp_dir, "subtitles.srt")
    
    logger.info(f"Generating TTS using voice {voice} (rate: {rate})")
    logger.info(f"Target audio path: {voiceover_path}")
    logger.info(f"Target subtitles path: {subtitles_path}")
    
    communicate = edge_tts.Communicate(script, voice, rate=rate)
    submaker = edge_tts.SubMaker()
    
    # Write audio stream and feed subtitle maker
    with open(voiceover_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)
                
    # Generate and write the SRT content
    srt_content = submaker.get_srt()
    with open(subtitles_path, "w", encoding="utf-8") as srt_file:
        srt_file.write(srt_content)
        
    logger.info("TTS and SRT subtitle generation completed successfully.")
    return voiceover_path, subtitles_path
