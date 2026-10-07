# ⚡ Tamil Nadu Google Places Lead Finder (Web Design Outreach)

An automated lead generation and qualification pipeline designed for web design agencies targeting high-reputation businesses in **Tamil Nadu** that have **no website listed on Google Maps**.

---

## 🎯 Lead Qualification Criteria

| Criteria | Value | Purpose |
|---|---|---|
| **Location** | Tamil Nadu (Chennai, Coimbatore, Madurai, Trichy, Salem, Tiruppur, Erode, Vellore, etc.) | Local, high-conversion geographic focus |
| **Rating** | $\ge 4.5\star$ | Proven customer satisfaction & trust |
| **Review Count** | $\ge 50$ (Up to $5,000+$) | Established customer volume and cash flow |
| **Website** | Missing / Empty | High-intent digital storefront opportunity |
| **Business Status** | `OPERATIONAL` | Active, currently open business |
| **Contact** | Direct Phone Number | Fast outreach via Call / WhatsApp |

---

## 📁 Project Structure

```
automating-shop/
├── .env.example            # Environment variables template
├── config.py               # Target cities, categories, & filtering thresholds
├── main.py                 # Unified master Python CLI for all operations
├── run.bat                 # Unified Windows Control Center runner
├── viewer.html             # Visual glassmorphism web dashboard
├── leads_data.js           # Embedded leads for viewer.html
├── leads_output/           # Generated CSV and Excel lead databases
├── core/                   # Engines, scrapers, outreach, and safety trackers
└── gmaps_scraper/          # Local Docker scraper container
```

---

---

## 🚀 How to Run

### Option A: Conor's Docker Scraper (Recommended: 100% Free, NO Credit Card Required!)

Since you have Docker on your PC, you can scrape live Google Maps data without any credit card or Google Cloud billing:

1. **Open Docker Desktop** on your PC.
2. **Start the Scraper container:**
   Run `run.bat start-docker` or:
   ```bash
   cd gmaps_scraper
   docker compose up -d
   ```
   *(This starts the Playwright scraping microservice on `http://localhost:8001`)*

3. **Run lead searches:**
   ```bash
   # Single city + category
   python main.py leads --city "Coimbatore" --category "salons"

   # Full Tamil Nadu curated matrix (Chennai, Coimbatore, Madurai, Salem, etc.)
   python main.py leads --preset tamil_nadu
   ```

4. **When you are done**, stop the container to free up RAM:
   Run `run.bat stop-docker` or:
   ```bash
   cd gmaps_scraper
   docker compose down
   ```

---

### Option B: Official Google Places API (If you have an API key)

If you ever obtain a Google Cloud API key:
1. Put your key in `.env`:
   ```env
   GOOGLE_PLACES_API_KEY=AIzaSy...your_key_here
   ```
2. Run with `--engine google`:
   ```bash
   python main.py leads --city "Trichy" --category "travel agencies" --engine google
   ```

---

### Option C: Instant Offline Demo Mode

```bash
python main.py leads --city "Coimbatore" --category "salons" --demo
```

The output is automatically saved as both **`.csv`** and **`.xlsx`** inside `leads_output/`.

---

## 🔍 Stage 2: Lead Verification (`verifier.py`)

As recommended in your workflow:
> *"No website listed on Google ≠ business definitely has no website."*

Run the verification assistant on your latest leads:

```bash
python main.py verify
```

- **Automated Web & Social Scan**: Automatically searches the business name and flags if social profiles or hidden domains exist.
- **Single-Key Actions**:
  - `[1]` Mark as **NO WEBSITE** (Confirmed lead)
  - `[2]` Mark as **SOCIAL ONLY** (Active Instagram/FB, but no booking website)
  - `[3]` Mark as **WEBSITE FOUND** (Disqualify from cold pitch)
  - `[4]` Mark as **UNCERTAIN**
  - `[o]` Open Google Search in your web browser with one keypress
  - `[q]` Save updates directly back into the CSV.

---

## 💻 Visual Web Dashboard (`viewer.html` & `dashboard.py`)

For a visual, glassmorphic command center:

```bash
python main.py dashboard
```

This launches `http://localhost:8521/viewer.html` in your browser where you can:
- View all leads organized by review count and lead score.
- Filter by City (Chennai, Coimbatore, Madurai, etc.) and Category.
- Filter by 🔥 **500+ Reviews Club**.
- Click **"🔍 Search"** or **"📸 Insta"** to cross-verify.
- Click **"💬 Pitch"** to auto-generate a tailored WhatsApp outreach message and copy it with 1 click.
- Export your verified list to a clean CSV.

---

## 💬 Outreach Scripts & Cold Email Generator (`outreach_generator.py`)

Generate natural, human-written pitches without sounding like automated spam or AI bots:

```python
from outreach_generator import generate_whatsapp_pitch, generate_email_pitch

lead = {
    "Business Name": "Zazzle Luxury Salon & Spa - Coimbatore",
    "City": "Coimbatore",
    "Verification Status": "HAS SOCIALS BUT NO WEBSITE"
}

email = generate_email_pitch(lead, sender_name="Krishna")
print(email["subject"]) # -> "Quick video preview: mobile template for Zazzle Luxury Salon & Spa"
print(email["subject_options"]) # -> ["Quick video preview: mobile template...", "Video preview for...", "Quick idea for...", "Mobile template preview..."]
print(email["body"])
```

### ✉️ Cold Emailing & High-Converting Subjects:
1. **Interactive Dashboard (`viewer.html`)**: Click **"✉️ Email"** on any lead card to see the improved dynamic high-open-rate subject (`⚡ High-Open Rate`), or switch with 1-click between 5 curated contextual subject chips (Quick Video Preview, City Video Preview, Quick Idea, Mobile Preview, Google Maps). The message offers a 15-second video recording of a clean mobile template from a previous client project. Click **"🔴 Open in Gmail Web ↗"** to compose immediately in Gmail.
2. **Re-Search All Shops for Gmail**:
   ```bash
   python main.py research
   # Or run via Control Center: run.bat research
   ```
   - Automatically crawls and re-searches all 767 leads for public business emails and Gmail addresses via social bios, targeted search queries, and directory listings with live DNS MX verification.
3. **Automated Sending**:
   ```bash
   python main.py mailer
   # Or run via Control Center: run.bat mailer
   ```
   - Automatically utilizes the high-converting subject line and configured sender name (`Krishna`) with Google App Password authentication.

---

## ⚡ Autonomous Outreach Engine (`core/auto_pilot.py`)

To continuously run the entire pipeline autonomously (**Scrape $\rightarrow$ Filter $\rightarrow$ Deduplicate $\rightarrow$ Send WhatsApp $\rightarrow$ Repeat**):

```bash
# Preview the continuous autonomous loop without sending:
python main.py autopilot --dry-run

# Run live autonomous pilot (20 messages/day safety limit):
python main.py autopilot --daily-limit 20

# Or run via Control Center: run.bat autopilot
```

### What AutoPilot Does:
1. **Target Rotation:** Cycles through high-utility retail and food shops (Restaurants $\rightarrow$ Meat shops $\rightarrow$ Bakeries $\rightarrow$ Sweet stalls) across Coimbatore, Chennai, Madurai, Trichy, Salem, etc.
2. **Master Deduplication:** Tracks every contacted business in `leads_output/master_outreach_tracker.csv`. Never messages the same business or phone number twice.
3. **Anti-Ban Protection & Fingerprinting:** Enforces letter-by-letter human typing simulation, randomized character pauses, mouse cursor jitter, fat-finger typo corrections, and randomized 35–65s human pauses between messages.
4. **Short Human-Like Messages:** Sends concise 3-line messages under 50 words that feel completely natural and conversational.

---

## 🛡️ Anti-Ban & High-Conversion Outreach Suite

### 1. Human Fingerprint Typing & WhatsApp Dispatcher
Bypasses WhatsApp bot detection by eliminating pre-filled message URLs and robotic copy-pasting. The browser navigates to the chat, focuses the message box, jitters the mouse, and types character-by-character with micro-pauses (30–95ms), sentence pauses (400–900ms), and human typo corrections (~6% error simulation with backspaces).

```bash
# Dry-run preview without launching browser:
python main.py whatsapp --dry-run

# Live dispatch with safe daily cap (e.g. 15 messages):
python main.py whatsapp --limit 15

# Send follow-up nudges to leads messaged >48 hours ago:
python main.py whatsapp --follow-up
```

### 2. Cross-Channel Daily Rate Limiter
Maintains an atomic state (`leads_output/rate_limit_state.json`) that resets daily at midnight:
- **WhatsApp Limit:** 20 messages/day (default)
- **Email Limit:** 50 messages/day (default)

```bash
# Inspect today's quota:
python main.py summary
```

### 3. Inbound Reply Tracking
Scans WhatsApp Web chats on login for incoming replies from leads. Automatically records reply snippets, tags status as `REPLIED`, updates timestamps, and advances the lead to the active reply queue.

### 4. 48-Hour Smart Follow-Up Scheduler
Detects leads contacted 48+ hours ago that have not replied and generates polite, non-pushy follow-up nudges (referencing their city and offering a short 15-second mobile preview). Strictly limited to 1 follow-up per shop.

```bash
# Preview or dispatch follow-ups:
python main.py whatsapp --follow-up --dry-run
python main.py whatsapp --follow-up
```

### 5. Conversion & Client Funnel Tracker
Tracks leads through an 8-stage sales pipeline:
`DISCOVERED` $\rightarrow$ `SENT` $\rightarrow$ `FOLLOW_UP_SENT` $\rightarrow$ `REPLIED` $\rightarrow$ `INTERESTED` $\rightarrow$ `VIDEO_SENT` $\rightarrow$ `CALL_SCHEDULED` $\rightarrow$ `CLIENT` (or `NOT_INTERESTED`).

```bash
# View funnel distribution in CLI:
python main.py funnel
```

*Note: In `viewer.html`, each lead card features an interactive stage dropdown that saves changes live via the dashboard API.*

### 6. A/B Message Variant Analytics
Tests and benchmarks outreach templates (`A_VIDEO_PITCH`, `B_DIRECT_OFFER`, `C_SOCIAL_PROOF`, etc.) by tracking reply and client conversion rates across all outreach records.

```bash
# View A/B performance leaderboard:
python main.py ab
```

### 7. Daily Operations & Outreach Summary
Generates an executive daily snapshot of pipeline health, newly scraped businesses, emails sent, WhatsApp messages delivered, inbound replies, pending 48h follow-ups, and channel quotas.

```bash
# Run daily summary:
python main.py summary
```

## 🎛️ Unified Control Center (`run.bat`)

All workflows have been consolidated into a single master batch runner: **`run.bat`**.

You can double-click **`run.bat`** to open the interactive numbered menu:
- `[1]` WhatsApp Outreach Bot (Anti-ban typing + 48h nudges)
- `[2]` Auto Cold Emailer (Zero approval, safe human pacing)
- `[3]` AutoPilot Continuous Engine (Scrape + Filter + Outreach loop)
- `[4]` Continuous Google Maps Scraper (Maps + Social lookup)
- `[5]` Re-Search All Shops for Gmail (Social bios & domain scan)
- `[6]` View Daily Operations Summary (KPIs & rate limits)
- `[7]` Sales Funnel & A/B Copy Performance Benchmarks
- `[8]` Launch Local Web Dashboard (`viewer.html` on port 8521)
- `[9]` Start Docker Scraper Container (`http://localhost:8001`)
- `[10]` Stop Docker Scraper Container (Free up RAM)
- `[11]` Configure Gmail SMTP Credentials & Test
- `[0]` Exit

### Direct Command-Line Shortcuts

You can also run any task directly from terminal without opening the menu:

| Shortcut | Action Executed |
|---|---|
| `run.bat whatsapp` | Launches WhatsApp sender, scans replies, and checks 48h follow-ups |
| `run.bat mailer` | Dispatches cold emails with zero approval and prints daily summary |
| `run.bat autopilot` | Launches autonomous continuous scrape $\rightarrow$ outreach engine |
| `run.bat scraper` | Launches continuous Google Maps and website discovery scraper |
| `run.bat research` | Crawls Instagram/Facebook bios and search engines for Gmail addresses |
| `run.bat summary` | Prints today's outreach performance and rate limit quotas |
| `run.bat funnel` | Displays conversion pipeline breakdown and A/B copy leaderboard |
| `run.bat dashboard` | Opens `http://localhost:8521/viewer.html` and starts local API server |
| `run.bat config-email` | Interactive setup for Gmail App Password & test sender |
| `run.bat stop-docker` | Stops Docker container to immediately release RAM |

---

## 🎖️ Acknowledgements & Credits

- **Google Maps Scraper Engine**: Built on and inspired by the FastAPI Google Maps scraping microservice created by [**@conor-is-my-name**](https://github.com/conor-is-my-name) ([n8n-autoscaling / Google Maps Scraper](https://github.com/conor-is-my-name/n8n-autoscaling)).
- **Automation & Headless Browser**: Powered by [Microsoft Playwright](https://playwright.dev/).
- **Terminal UI**: Powered by [Rich](https://github.com/Textualize/rich).


