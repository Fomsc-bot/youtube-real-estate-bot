# 🌌 The Universe — Automated YouTube Shorts Pipeline

> **A fully automated NASA/Space Shorts channel hosted entirely on GitHub Actions.**
> Uploads a new 15–30 second space fact Short every day using real NASA imagery,
> Gemini AI narration scripts, edge-tts voiceover, and FFmpeg video assembly.

---

## 📡 What It Does

| Day | Content | Source |
|-----|---------|--------|
| Mon–Fri & Sun | **"Today in Space"** — NASA Astronomy Picture of the Day | [NASA APOD API](https://api.nasa.gov/) |
| Saturday | **"Asteroid Watch"** — closest NEO passing Earth this week | [NASA NEO API](https://api.nasa.gov/) |

**Pipeline steps (in order):**
1. `fetch_content.py` — Download APOD image + metadata from NASA
2. `generate_script.py` — Generate 50–72 word narration via Google Gemini
3. `generate_audio.py` — TTS voiceover via `edge-tts` (Aria Neural voice) + word timestamps
4. `build_video.py` — FFmpeg: 9:16 crop, animated captions, logo overlay, hook text
5. `generate_metadata.py` — SEO title, description, hashtags, tags
6. `upload_video.py` — YouTube Data API v3 upload with resumable chunks
7. `reply_comments.py` — Auto-reply to new comments using Gemini (runs 3h later)

---

## 🔑 Required API Keys & Secrets

You need **4 secrets** in your GitHub repository:

### 1. `NASA_API_KEY` (Free)
- Register instantly at **https://api.nasa.gov/**
- Click **"Generate API Key"**
- You'll receive the key by email within seconds
- Without it, the pipeline falls back to `DEMO_KEY` (30 requests/hour — usually enough)
- Add to GitHub: Repo → Settings → Secrets → `NASA_API_KEY`

### 2. `GEMINI_API_KEY`
- Get it from **https://aistudio.google.com/app/apikey**
- Free tier: 1,500 requests/day — more than enough for 1 video/day
- Add to GitHub: `GEMINI_API_KEY`

### 3. `YOUTUBE_CREDENTIALS_JSON` (OAuth2 — already configured)
This secret holds your YouTube OAuth2 credentials as a base64-encoded JSON string.
It was migrated from the previous pipeline. Format:
```json
{
  "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
  "client_secret": "YOUR_CLIENT_SECRET",
  "refresh_token": "YOUR_REFRESH_TOKEN",
  "token_uri": "https://oauth2.googleapis.com/token"
}
```
If you need to regenerate it, see the **[Re-generating OAuth2 Credentials](#re-generating-oauth2-credentials)** section below.

---

## 🚀 Setup

### Step 1 — Clone & configure
```bash
git clone https://github.com/Fomsc-bot/youtube-real-estate-bot.git
cd youtube-real-estate-bot
cp .env.example .env
# Edit .env with your local API keys for testing
```

### Step 2 — Install dependencies (local testing)
```bash
pip install -r requirements.txt
# Also install FFmpeg:
# Windows: winget install ffmpeg  OR  choco install ffmpeg
# Ubuntu:  sudo apt-get install ffmpeg
# macOS:   brew install ffmpeg
```

### Step 3 — Add GitHub Secrets
Go to your repo on GitHub → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret Name | Value |
|-------------|-------|
| `NASA_API_KEY` | Your NASA API key |
| `GEMINI_API_KEY` | Your Gemini API key |
| `YOUTUBE_CREDENTIALS_JSON` | Base64-encoded credentials JSON (see above) |

### Step 4 — Add your channel logo
Replace `assets/logo.png` with your actual channel logo (PNG with transparency, any size — it'll be resized to 90×90px).

### Step 5 — Push and test
```bash
git add .
git commit -m "feat: The Universe pipeline setup"
git push origin main
```
Then go to **GitHub Actions** → **🌌 The Universe — Daily Shorts Upload** → **Run workflow** → set **"Dry run"** to `true` first to verify everything works without uploading.

---

## 🧪 Running Locally (Testing Each Step)

Each module is independently runnable via CLI:

```bash
# Step 1: Fetch today's APOD
python src/fetch_content.py --output output/

# Step 2: Generate narration script
python src/generate_script.py --apod output/apod.json --output output/script.json

# Step 3: Generate TTS audio
python src/generate_audio.py --script output/script.json --output output/

# Step 4: Build video
python src/build_video.py \
  --image output/apod_image.jpg \
  --audio output/narration.mp3 \
  --vtt output/narration.vtt \
  --script output/script.json \
  --output output/final_video.mp4

# Step 5: Generate metadata
python src/generate_metadata.py --apod output/apod.json --script output/script.json

# Step 6: Upload (add --dry-run to skip actual upload)
python src/upload_video.py --video output/final_video.mp4 --metadata output/metadata.json --dry-run

# Run the full pipeline locally
python main.py --dry-run   # No API calls, uses fixture data
python main.py             # Full real run
python main.py --neo       # Force Asteroid Watch mode
python main.py --date 2024-07-04  # Use specific APOD date
```

---

## ⏰ Schedule

| Workflow | Cron | UTC Time | IST Time |
|----------|------|----------|----------|
| Daily Upload | `0 14 * * *` | 2:00 PM | 7:30 PM |
| Comment Replies | `0 17 * * *` | 5:00 PM | 10:30 PM |

To change the posting time, edit `cron` in `.github/workflows/daily_upload.yml`.

---

## ⚙️ Configuration (`config.yaml`)

Key tunables — no code changes needed:

```yaml
audio:
  voice_id: "en-US-AriaNeural"   # Change voice here

video:
  caption_font_size: 58          # Caption text size
  logo_opacity: 0.65             # Logo transparency

metadata:
  hashtag_pool:
    broad: ["#space", "#nasa", "#shorts"]
    niche: ["#apod", "#astronomy", "#cosmos"]
```

---

## 🔄 Re-generating OAuth2 Credentials

If your refresh token expires:

1. Go to **Google Cloud Console** → APIs & Services → Credentials
2. Ensure YouTube Data API v3 is enabled
3. Download your OAuth2 client secrets JSON ("Desktop app" type)
4. Run the helper locally:
   ```bash
   python src/setup_oauth.py --client-secrets /path/to/client_secrets.json
   ```
5. A browser window opens — log in as the channel owner
6. Copy the base64 string output and update the `YOUTUBE_CREDENTIALS_JSON` secret

---

## 📁 Repository Structure

```
.
├── .github/
│   └── workflows/
│       ├── daily_upload.yml      # Main pipeline (runs daily at 2PM UTC)
│       └── reply_comments.yml    # Comment reply (runs 3h after upload)
├── assets/
│   ├── logo.png                  # Channel logo (replace with your own)
│   └── fonts/
│       └── Montserrat-Bold.ttf   # Caption font (auto-downloaded in CI)
├── src/
│   ├── fetch_content.py          # Step 1: NASA APOD/NEO API
│   ├── generate_script.py        # Step 2: Gemini script generation
│   ├── generate_audio.py         # Step 3: edge-tts voiceover
│   ├── build_video.py            # Step 4: FFmpeg video assembly
│   ├── generate_metadata.py      # Step 5: YouTube metadata
│   ├── upload_video.py           # Step 6: YouTube Data API upload
│   ├── reply_comments.py         # Step 7: Auto comment replies
│   └── setup_oauth.py            # One-time OAuth2 helper
├── output/                       # Generated files (gitignored)
├── config.yaml                   # All tunables
├── main.py                       # Pipeline orchestrator
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🛡️ Content Integrity Guarantees

- **No AI-generated visuals** — only real NASA APOD imagery
- **No fabricated facts** — Gemini is strictly instructed to use only APOD-provided text
- **`containsSyntheticMedia: false`** — correctly disclosed since all imagery is real NASA content
- **`selfDeclaredMadeForKids: false`** — space education for general audiences

---

## 🐛 Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `DEMO_KEY rate limit` | No NASA_API_KEY | Register at api.nasa.gov (free) |
| `GEMINI_API_KEY not set` | Missing secret | Add `GEMINI_API_KEY` to GitHub Secrets |
| `YouTube quota exceeded (403)` | 10,000 units/day limit hit | Wait 24h; uploads cost ~1,600 units each |
| `FFmpeg filter error` | APOD returned unusual image | Run `--dry-run` to isolate; check `output/` artifacts |
| `Refresh token invalid` | OAuth2 expired | Re-run `setup_oauth.py` locally |
| `APOD returned a video` | NASA published a video today | Pipeline auto-falls-back to yesterday's image |

---

## 📊 Estimated API Costs

| Service | Usage | Cost |
|---------|-------|------|
| NASA APOD | 1 req/day | Free |
| Google Gemini | ~2 calls/day | Free tier (1,500 req/day) |
| edge-tts | 1 call/day | Free (Microsoft Edge TTS) |
| YouTube Data API | ~1,600 units/day | Free (10,000 unit quota) |
| GitHub Actions | ~5–10 min/day | Free (2,000 min/month for public repos) |

**Total cost: $0/month** with free tiers.

---

*Built for [The Universe](https://youtube.com) channel. Real NASA imagery. Real science.*
