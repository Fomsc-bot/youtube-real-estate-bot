# Automated YouTube Shorts Real Estate Market Insights Bot

A fully automated Python-based YouTube Shorts creation and posting channel system. Powered by the Rentcast API for real market data, Edge-TTS for high-quality free voice synthesis, Pillow for glassmorphic visual overlays, MoviePy for video compilation, and the YouTube Data API v3 for automated video uploading. The system runs entirely on a daily cron schedule via GitHub Actions.

---

## 🌟 Features

- **Dynamic Data Rotation**: Rotates daily through 5 major US cities (Austin TX, Phoenix AZ, Miami FL, Nashville TN, Charlotte NC).
- **Punchy Script Generator**: Dynamically crafts 90-110 word script transcripts (45-55s duration) highlighting exact MoM trends. Supports A/B title/hook template testing.
- **High-Quality Free TTS**: Uses Microsoft Edge-TTS (`en-US-AriaNeural`) with speed adjustments (+5%) for engaging social media flow.
- **Word-Level Subtitles**: Generates a standard `.srt` subtitle file and burns bold yellow captions with thick black outlines onto the video.
- **Glassmorphic UI Engine**: Uses Pillow to draw a premium vertical gradient background and translucent rounded stat cards (no ImageMagick dependency).
- **Resumable Uploader**: Implements resumable chunk video uploading with HTTP retries and exponential backoff.
- **Zero-State Automation**: Runs from a cold virtual machine runner in GitHub Actions, caching API responses locally to save monthly request quotas.

---

## 📂 Project Structure

```text
youtube-real-estate-bot/
├── .github/
│   └── workflows/
│       └── daily_upload.yml       # GitHub Actions scheduled workflow
├── assets/
│   └── music/
│       └── README.md              # Instructions for adding background audio tracks
├── src/
│   ├── __init__.py
│   ├── fetch_data.py              # Rentcast API client (caching, fallbacks, retries)
│   ├── script_generator.py        # Punchy Shorts voiceover script generator
│   ├── tts.py                     # Microsoft Edge-TTS voice & subtitles synthesis
│   ├── video_builder.py           # Pillow overlays and MoviePy video compile engine
│   └── uploader.py                # Google YouTube Data API resumable video uploader
├── main.py                        # Orchestrator entrypoint
├── requirements.txt               # Pinned Python package dependencies
├── .env.example                   # Local environment variables template
└── README.md                      # Main project documentation (this file)
```

---

## ⚙️ Setup and Installation

### 1. Prerequisite Accounts
- **Rentcast API Key**: Register at [developers.rentcast.io](https://developers.rentcast.io) and copy your free API key (includes 50 requests/month).
- **Google Cloud Platform Project**: Create a GCP project at [console.cloud.google.com](https://console.cloud.google.com) and enable the **YouTube Data API v3**.

### 2. YouTube OAuth2 Credentials (Refresh Token) Setup
YouTube Data API v3 requires user consent authorization (not service accounts) for personal channel uploads:
1. Go to **APIs & Services > Credentials** in GCP console.
2. Click **Create Credentials > OAuth client ID** (select *Desktop Application* or *Web Application*).
3. Download the credentials JSON file.
4. Run a local python script to authorize access and save the credential containing the `refresh_token`. The JSON structure needs to look like this:
   ```json
   {
     "client_id": "YOUR_CLIENT_ID",
     "client_secret": "YOUR_CLIENT_SECRET",
     "refresh_token": "YOUR_REFRESH_TOKEN",
     "token_uri": "https://oauth2.googleapis.com/token"
   }
   ```
5. Convert this JSON text into a base64 string:
   - On Linux/macOS: `cat credentials.json | base64 -w 0`
   - On Windows (PowerShell): `[Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content credentials.json -Raw)))`
6. Copy this base64 string. It will be used as the `YOUTUBE_CREDENTIALS_JSON` secret.

### 3. GitHub Secrets Configuration
In your repository, navigate to **Settings > Secrets and variables > Actions** and add the following Repository Secrets:
- `RENTCAST_API_KEY`: Your Rentcast API key.
- `YOUTUBE_CREDENTIALS_JSON`: The base64-encoded YouTube credentials JSON string.

### 4. Background Music
Place background music `.mp3` tracks inside `assets/music/`. If this folder is empty, the bot compiles videos using the voiceover only.

---

## 💻 Local Run & Testing

To run the pipeline locally:
1. **Clone the project** and navigate to the folder:
   ```bash
   cd youtube-real-estate-bot
   ```
2. **Install Python 3.11** and setup dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure local environment**:
   - Copy `.env.example` to `.env`.
   - Fill in your `RENTCAST_API_KEY` and base64-encoded `YOUTUBE_CREDENTIALS_JSON`.
   - *Note*: If `YOUTUBE_CREDENTIALS_JSON` is empty, the bot runs in **Dry-Run mode** (renders the video locally but skips uploading).
4. **Execute orchestrator**:
   ```bash
   python main.py
   ```

The final video file will be generated in your system's temporary folder (`/tmp/final_short.mp4` on Unix or `Temp\final_short.mp4` on Windows).

---

## 🤖 GitHub Actions Automation

The automation runs using the daily workflow:
- **Cron Trigger**: Runs every day at **2 PM UTC** (9 AM EST), aligning with peak real estate viewer activity in the US.
- **Manual Trigger**: Supports the `workflow_dispatch` event, allowing you to click "Run workflow" from the Actions tab on GitHub.

---

## 📈 Growth & YouTube Shorts Monetization Strategy

### 1. Schedule Optimization
- **Optimal Time**: Daily at 2:00 PM UTC (9:00 AM EST). This hits East Coast office hours and West Coast mornings, maximizing initial swipe-through rates.
- **Posting Frequency**: 1-3 times daily. You can adjust the GitHub Actions cron to trigger twice daily (e.g. 2 PM and 8 PM UTC) if desired.

### 2. SEO & Hook Blueprint
- **Title Structure**: Start titles with emojis and high-contrast numbers (e.g., `🏠 Austin Real Estate Update June 08 | Rent down 1.2% #Shorts`). Keep titles under 100 characters.
- **A/B Hook Testing**: Alternate your hooks. The bot automatically alternates script formats:
  - **Template A**: Highlights a shocking percentage increase/decrease ("Rents in Miami just dropped 2.5%!").
  - **Template B**: Opens with a provocative question ("Is the Phoenix housing market crashing?").
- **Hashtag Strategy**: Use the local city hashtag (e.g., `#austinrealestate` or `#charlotterealestate`) alongside broad hashtags. This targets localized search interest.

### 3. Engagement Tactics
- **Pinned Comment**: Pin a comment immediately after posting, asking: *"Would you buy or rent in [City] today? Let me know below!"* This prompts discussions, boosting the video's virality.
- **Video Cover Frame**: While YouTube Shorts do not support custom upload thumbnails, the visual design uses a bold, high-contrast title card at the start, ensuring a premium scroll-stopper.

### 4. Monetization Policy (2024 onwards)
To start earning ad revenue from the YouTube Partner Program, you need:
- **1,000 Subscribers**
- **10 Million Shorts views** within 90 days (or 4,000 valid public watch hours on long-form videos).

*Estimated Revenue*: RPM for real estate Shorts ranges from **$0.03 to $0.07** per 1,000 views. Hits on high CPM areas (like home buying and mortgage rates) can lead to **$300 to $700** monthly at 10M views/month, in addition to brand sponsorship opportunities.
