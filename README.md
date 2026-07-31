# 🚀 Viral YouTube Shorts Pipeline (MoneyPrinterTurbo + Remotion Architecture)

> **Fully automated viral YouTube Shorts generation & publishing bot built for maximum view retention and subscriber conversion.**

Inspired by **[MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo.git)** (viral psychological hooks, sentence-by-sentence stock video alignment, audio ducking BGM) and **[Remotion](https://github.com/remotion-dev/remotion.git)** (dynamic word-by-word karaoke captions, animated subscribe overlays, video progress bars).

---

## 🌟 Key Features

- 🎯 **Viral Hook Script Engine (MoneyPrinterTurbo)**: First 3 seconds pattern interrupt & curiosity gap powered by Gemini AI.
- 🎬 **Multi-Clip Visual Fetching (Pexels API)**: Sentence-by-sentence keyword extraction automatically downloads matching 9:16 vertical HD stock video clips.
- 🎨 **Remotion Motion Graphics Compositor**:
  - **Dynamic Word-by-Word Karaoke Subtitles**: Active word highlighting in neon yellow with bold outlines.
  - **Animated SUBSCRIBE Conversion Badge**: Displays a call-to-action badge pop-up during the video ending to drive subscriber growth.
  - **Top Progress Bar Overlay**: Visual duration indicator keeping viewers watching until the end (maximizes Average View Duration).
- 🎵 **Background Music (BGM) & Audio Ducking**: Smooth blend of speech narration with ambient background audio loops.
- 📌 **Viral YouTube SEO & Subscriber Pinned Comment**: Generates high-CTR curiosity titles, targeted hashtag stacks, and pinned comment prompts to boost engagement.
- 🏠 **Multi-Niche Flexibility**: Supports **Real Estate & Luxury Mansions** (`real_estate`) and **Space Facts & NASA APOD** (`space`).

---

## 📡 Pipeline Architecture

```
1. src/generate_script.py   -> Gemini AI viral script (Hook + Sentence Keywords + CTA)
2. src/fetch_content.py     -> MoneyPrinterTurbo multi-clip Pexels HD stock video fetcher
3. src/generate_audio.py    -> gTTS voiceover + WebVTT karaoke timestamps + Ambient BGM
4. src/build_video.py       -> Remotion video compositor (karaoke text, subscribe badge, progress bar)
5. src/generate_metadata.py -> High-CTR Title, Hashtags, and Pinned Comment
6. src/upload_video.py      -> YouTube Data API v3 upload + auto-pinned comment
```

---

## 🔑 Required & Optional API Keys

Add these to your **GitHub Repository Secrets** or local `.env` file:

| Secret Name | Required? | Description |
|-------------|-----------|-------------|
| `GEMINI_API_KEY` | **Required** | Script generation & viral hook creation ([Get API Key](https://aistudio.google.com/app/apikey)) |
| `YOUTUBE_CREDENTIALS_JSON` | **Required** | YouTube OAuth2 credentials JSON for automated channel uploads |
| `PEXELS_API_KEY` | *Optional* | Fetch HD real estate / topic stock videos per sentence ([Get Free API Key](https://www.pexels.com/api/)). If omitted, procedural high-res visual cards are generated automatically. |
| `NASA_API_KEY` | *Optional* | NASA APOD data for Space niche |

---

## 🚀 Running & Testing

### Local Dry-Run (No API usage or uploads)
```bash
python main.py --dry-run
```

### Run for Real Estate Niche (Default)
```bash
python main.py --niche real_estate
```

### Run for Space Niche
```bash
python main.py --niche space
```

### Test Individual Pipeline Modules
```bash
python src/generate_script.py --niche real_estate --dry-run
python src/fetch_content.py --dry-run
python src/generate_audio.py --dry-run
python src/build_video.py --dry-run
python src/generate_metadata.py --dry-run
```

---

## ⚙️ Configuration (`config.yaml`)

Edit `config.yaml` to customize video styling, karaoke fonts, colors, and background music without code changes:

```yaml
niche:
  default: "real_estate"

stock_visuals:
  pexels_api_env: "PEXELS_API_KEY"
  clips_per_script: 4

audio:
  bgm_enabled: true
  bgm_volume: 0.15

video:
  karaoke_subtitles: true
  caption_highlight_color: "yellow"
  subscribe_badge: true
  progress_bar: true
```

---

## 📊 Summary of Enhancements for Views & Subscriber Growth

1. **3-Second Hook Rule**: Swiping away stops instantly due to high-curiosity verbal/visual pattern interrupts.
2. **Multi-Clip Dynamic Motion**: Scene changes every 3 seconds keep retention graphs high.
3. **Word-by-Word Karaoke Captions**: Viewers read along with high visual impact, increasing watch time.
4. **Subscribe Conversion Overlay & Pinned Comment**: Drives casual viewers into subscribers.
