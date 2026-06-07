import os
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load local .env file if it exists
load_dotenv()

# Setup logging with timestamp
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("MainOrchestrator")

from src.fetch_data import get_current_city, get_market_stats, get_hot_listings
from src.script_generator import generate_script, get_hook_stat
from src.tts import generate_tts
from src.video_builder import build_video
from src.uploader import upload_to_youtube

async def main():
    start_time = datetime.now()
    logger.info("==================================================")
    logger.info("🚀 Starting YouTube Shorts Real Estate Bot Pipeline")
    logger.info("==================================================")
    
    try:
        # Step 1: Select and fetch market data for today's rotating city
        logger.info("[Step 1/5] Fetching market data...")
        city_info = get_current_city()
        city = city_info["city"]
        state = city_info["state"]
        zipcode = city_info["zip"]
        
        stats_data = get_market_stats(city, state)
        logger.info(f"Market stats retrieved for {city}: Median Price: ${stats_data['medianPrice']:,}, Median Rent: ${stats_data['medianRent']:,}")
        
        # Step 2: Generate script and hook title from data
        logger.info("[Step 2/5] Generating voiceover script...")
        script = generate_script(stats_data)
        hook_stat = get_hook_stat(stats_data)
        
        # Step 3: Synthesize Text-to-Speech voiceover and SRT subtitles
        logger.info("[Step 3/5] Generating speech and word-level timestamps...")
        voiceover_path, subtitles_path = await generate_tts(script)
        logger.info(f"TTS Audio: {voiceover_path}")
        logger.info(f"SRT Subtitles: {subtitles_path}")
        
        # Step 4: Build vertical H.264 video
        logger.info("[Step 4/5] Building vertical 1080x1920 video clip...")
        video_path = build_video(city, state, stats_data, voiceover_path, subtitles_path)
        logger.info(f"Video file generated: {video_path}")
        
        # Step 5: Upload video to YouTube channel
        logger.info("[Step 5/5] Uploading video to YouTube...")
        video_title, video_url = upload_to_youtube(video_path, city, state, stats_data, hook_stat)
        
        # Success summary
        end_time = datetime.now()
        duration = end_time - start_time
        logger.info("==================================================")
        logger.info("🎉 BOT PIPELINE COMPLETED SUCCESSFULLY!")
        logger.info(f"Total Time: {duration.total_seconds():.2f} seconds")
        logger.info(f"Video Title: {video_title}")
        logger.info(f"YouTube Shorts URL: {video_url}")
        logger.info("==================================================")
        
    except Exception as e:
        logger.exception("❌ PIPELINE RUN FAILED WITH EXCEPTION:")
        raise e

if __name__ == "__main__":
    asyncio.run(main())
