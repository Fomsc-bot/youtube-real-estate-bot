import os
import base64
import json
import random
import time
import logging
from datetime import datetime
import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

def clean_percentage(val):
    return abs(round(val * 100, 1))

def get_youtube_service():
    """Build YouTube service from base64 encoded credentials secret."""
    creds_b64 = os.environ.get("YOUTUBE_CREDENTIALS_JSON")
    if not creds_b64:
        logger.warning("YOUTUBE_CREDENTIALS_JSON environment variable is not set. Bypassing upload (DRY RUN mode).")
        return None
        
    try:
        decoded_json = base64.b64decode(creds_b64).decode('utf-8')
        creds_data = json.loads(decoded_json)
    except Exception as e:
        logger.error(f"Failed to base64 decode and parse YOUTUBE_CREDENTIALS_JSON: {e}")
        return None

    try:
        # Check if the credentials correspond to an OAuth2 client with a refresh token
        if "refresh_token" in creds_data:
            logger.info("Found refresh token. Authenticating using User OAuth2 credentials...")
            credentials = Credentials(
                token=creds_data.get("access_token"),
                refresh_token=creds_data.get("refresh_token"),
                client_id=creds_data.get("client_id"),
                client_secret=creds_data.get("client_secret"),
                token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token")
            )
        elif "type" in creds_data and creds_data["type"] == "service_account":
            logger.info("Found service account type. Authenticating using Service Account credentials...")
            credentials = service_account.Credentials.from_service_account_info(
                creds_data,
                scopes=["https://www.googleapis.com/auth/youtube.upload"]
            )
        else:
            # Alternative format (e.g. client secrets file format with nested web/installed client credentials)
            logger.info("Credentials format matches standard client secrets. Authenticating...")
            # If nested under 'installed' or 'web'
            key = "installed" if "installed" in creds_data else "web" if "web" in creds_data else None
            if key:
                inner_data = creds_data[key]
                credentials = Credentials(
                    token=inner_data.get("access_token"),
                    refresh_token=inner_data.get("refresh_token"),
                    client_id=inner_data.get("client_id"),
                    client_secret=inner_data.get("client_secret"),
                    token_uri=inner_data.get("token_uri", "https://oauth2.googleapis.com/token")
                )
            else:
                raise ValueError("Could not determine credential structure.")
                
        return build("youtube", "v3", credentials=credentials)
    except Exception as e:
        logger.error(f"Failed to initialize YouTube API client: {e}")
        return None

def upload_to_youtube(video_path, city, state, stats_data, hook_stat):
    """
    Upload a vertical Shorts MP4 video to YouTube.
    Title format: "🏠 {City} Real Estate Update {Month Day} | {hook_stat} #Shorts"
    Includes 15 hashtags and 15 tags, and implements resumable chunks upload.
    Returns: (video_title, video_url)
    """
    # 1. Format dynamic dates
    month_day = datetime.now().strftime("%B %d")
    
    # 2. Format title
    title = f"🏠 {city} Real Estate Update {month_day} | {hook_stat} #Shorts"
    if len(title) > 100:
        title = title[:96] + "..."
        
    # 3. Format description
    price = f"${stats_data['medianPrice']:,}"
    rent = f"${stats_data['medianRent']:,}"
    
    sale_mom = stats_data["saleMoM"]
    rent_mom = stats_data["rentalMoM"]
    
    sale_change_sign = "+" if sale_mom >= 0 else "-"
    rent_change_sign = "+" if rent_mom >= 0 else "-"
    
    sale_change_val = clean_percentage(sale_mom)
    rent_change_val = clean_percentage(rent_mom)
    
    new_listings = stats_data["newListings"]
    total_listings = stats_data["totalListings"]
    
    city_hashtag = city.replace(" ", "").lower()
    
    description = (
        f"🏠 {city} Real Estate Market Update - {month_day}\n\n"
        f"Here are the latest local real estate market data points:\n"
        f"📍 Median Home Price: {price} ({sale_change_sign}{sale_change_val}% MoM)\n"
        f"📍 Median Monthly Rent: {rent} ({rent_change_sign}{rent_change_val}% MoM)\n"
        f"📍 Market Inventory: {total_listings:,} active listings ({new_listings:,} new listings this week)\n\n"
        f"Disclaimer: Real estate statistics are aggregate averages and are subject to market changes. "
        f"This content is for informational and educational purposes only and does not constitute financial, "
        f"tax, or investment advice.\n\n"
        f"Hashtags:\n"
        f"#realestate #housingmarket #shorts #investing #renttrends #homebuying #realestateinvesting "
        f"#{city_hashtag} #propertymarket #realestatetips #housingcrisis #mortgage #firsttimehomebuyer "
        f"#renters #realestateinvestor"
    )
    
    # 4. Define 15 tags
    tags = [
        "realestate", "housingmarket", "shorts", "investing", "renttrends", "homebuying", 
        "realestateinvesting", city.lower(), "propertymarket", "realestatetips", "housingcrisis", 
        "mortgage", "firsttimehomebuyer", "renters", "realestateinvestor"
    ]
    
    logger.info(f"Video Title: {title}")
    
    youtube = get_youtube_service()
    if not youtube:
        logger.warning("YouTube API service not configured (DRY RUN). Skipping upload.")
        return title, "https://www.youtube.com/shorts/dry_run_mode_no_upload"
        
    logger.info(f"Uploading file {video_path} to YouTube in resumable mode...")
    
    # 5. Media upload with 5MB chunks
    media = MediaFileUpload(video_path, chunksize=5*1024*1024, resumable=True, mimetype="video/mp4")
    
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "22",  # Category: People & Blogs
                "defaultLanguage": "en"
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        },
        media_body=media
    )
    
    max_retries = 5
    response = None
    retry = 0
    
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                logger.info(f"Upload Progress: {progress}%")
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                retry += 1
                if retry > max_retries:
                    raise e
                sleep_time = random.random() * (2 ** retry)
                logger.warning(f"YouTube server error {e.resp.status}. Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
            else:
                raise e
        except (requests.exceptions.RequestException, IOError) as e:
            retry += 1
            if retry > max_retries:
                raise e
            sleep_time = random.random() * (2 ** retry)
            logger.warning(f"Network error {e}. Retrying in {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)
            
    video_id = response.get("id", "unknown")
    video_url = f"https://www.youtube.com/shorts/{video_id}"
    logger.info(f"Video uploaded successfully. Video ID: {video_id}, URL: {video_url}")
    
    return title, video_url
