# 💜 BTS Spotlight — Viral YouTube Shorts Automation Pipeline

> **A BTS-focused YouTube Shorts pipeline built to run on GitHub Actions using free-tier services.** Free quotas, API eligibility, and service terms can change; this project cannot guarantee $0 operation forever or guarantee viral reach.

Inspired by **[MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo.git)** (viral psychological hooks, sentence-by-sentence visual alignment, audio ducking BGM) and **[Remotion](https://github.com/remotion-dev/remotion.git)** (dynamic word-by-word karaoke captions, animated subscribe conversion overlays, video progress bars).

---

## 🔒 100% Strict BTS-Only Content Guardrail

This pipeline is strictly locked to **BTS only**:
- **Topic Scope:** Only BTS (Bangtan Sonyeondan) group achievements, Guinness World Records, Billboard milestones, album eras (*Love Yourself, Map of the Soul, BE, Proof*), and member updates for **RM (Kim Namjoon), Jin (Kim Seokjin), SUGA (Min Yoongi / Agust D), J-Hope (Jung Hoseok), Jimin (Park Jimin), V (Kim Taehyung), and Jungkook (Jeon Jungkook)**.
- **Source and relevance checks:** Scheduled BTS scripts require a recent RSS story, a valid Gemini response, and a BTS relevance check. If a source or script is unavailable, the run fails instead of recycling an old claim.

---

## 💡 $0 Cost Architecture (Zero External Infrastructure)

- ❌ **No S3 buckets:** Videos are generated locally in temporary disk (`output/`) and streamed directly to YouTube via YouTube Data API v3.
- ❌ **No database:** No PostgreSQL, MySQL, Redis, or Prisma required.
- ❌ **No Telegram bot:** Clean, standard GitHub Actions run logs and artifact tracking.
- **No project database or Docker required** for this Python scheduled workflow.
- Uses GitHub-hosted Actions runners, Gemini API, gTTS, FFmpeg, Pillow, and YouTube Data API. These have free tiers or no direct charge, subject to current quotas, eligibility, and terms.

---

## 🌟 Key Features

- 🎯 **Viral BTS Hook Script Engine**: 3-second pattern interrupts, record-breaking facts, and emotional ARMY moments.
- 🎬 **Multi-Clip Visuals & Aesthetic Cards**: Generates high-res purple-and-gold BTS visual cards or downloads concert/stage clips matching every sentence.
- 🎨 **Motion Graphics Compositor**:
  - **Dynamic Karaoke Subtitles**: Word-by-word active highlighting with drop shadows.
  - **Animated SUBSCRIBE Conversion Badge**: Pop-up banner driving casual viewers to subscribe.
  - **Top Progress Bar Overlay**: Visual indicator keeping viewers watching until the end.
- 🎵 **Background Audio & Ducking**: Speech narration smoothly blended with ambient music.
- **Source-linked metadata:** Generates a concise title, a few relevant hashtags, a source link, and a story-specific viewer question in the description.
- 💬 **Automated Comment Replies**: Automatically engages with fans and answers comments in a warm ARMY persona.

---

## 📡 Pipeline Architecture

```
1. src/generate_script.py   -> Gemini AI BTS script + strict BTS relevance guardrail
2. src/fetch_content.py     -> Original editorial cards for BTS stories
3. src/generate_audio.py    -> gTTS voiceover + WebVTT karaoke timestamps + BGM
4. src/build_video.py       -> FFmpeg video compositor (karaoke text, subscribe badge, progress bar)
5. src/generate_metadata.py -> Source-linked title, hashtags, and viewer question
6. src/upload_video.py      -> Direct YouTube Data API v3 upload
7. src/reply_comments.py    -> Auto-replies warmly to ARMY comments 3 hours later
```

---

## 🔑 Credentials in GitHub Secrets

Add these to your **GitHub Repository Secrets** (Settings → Secrets and variables → Actions):

| Secret Name | Required? | Used for |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | **Required** | Source-bound script generation. Gemini quotas and free-tier terms apply. |
| `YOUTUBE_CREDENTIALS_JSON` | **Required** | Base64-encoded YouTube OAuth2 credentials for publishing. |

---

## 🚀 Running & Automation

### Automated Daily Uploads (GitHub Actions)
The workflow in `.github/workflows/daily_upload.yml` runs daily on schedule (12:30 UTC) or can be triggered manually:
1. Go to your repository on GitHub.
2. Click **Actions → 💜 BTS Spotlight — Daily Shorts Upload → Run workflow**.
3. Click **Run workflow**. Scheduled and manual runs publish BTS-only content when a recent source item and valid script are available.

For the editorial changes and Studio metrics to review, see [the BTS Shorts growth playbook](docs/BTS_GROWTH_PLAYBOOK.md).

### Local Testing (Dry Run)
Test the entire pipeline locally without calling external APIs or uploading to YouTube:
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Test dry-run
python main.py --dry-run
```
