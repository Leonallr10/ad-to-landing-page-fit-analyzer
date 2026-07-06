# SIGNAL — Ad-to-Landing Page Fit Analyzer

Compare ad copy against landing page copy and find **message-match gaps** before you spend ad budget. Paste your ads and page text, get scored dimensions, gap notes, fixes, and tailored hero suggestions per ad angle.

> Scores are directional judgments from a language model reading pasted copy — not a certified audit. Validate findings with real click-through and conversion data.

---

## What it does

When someone clicks an ad, they expect the landing page to **continue the same promise immediately**. This tool checks whether that continuity holds across six marketing dimensions and highlights where the story breaks.

**Inputs**

- **1–5 ad copies** — headline, primary text, CTA (transcribe from screenshots; images are not read)
- **Landing page copy** — pasted in reading order, hero/above-the-fold first
- **Landing page URL** — optional, reference only (the app does **not** fetch live pages)

**Outputs**

- Overall **summary**
- **Per-ad report** — scores, gap notes, top fix, verdict
- **Angle clusters** — groups ads by messaging angle (e.g. *Pain-point led*, *Social proof led*)
- **Suggested hero sections** — headline, subhead, proof line, and CTA tailored per angle

---

## Architecture

```
┌─────────────┐     POST /analyze      ┌──────────────┐     Groq API      ┌─────────────┐
│  frontend/  │  ──────────────────►  │  backend/    │  ─────────────►  │  LLM        │
│  index.html │  ◄──────────────────  │  FastAPI     │  ◄─────────────  │  (Groq)     │
└─────────────┘     JSON results       └──────────────┘                   └─────────────┘
```

- **Frontend** — static HTML/CSS/JS, no build step
- **Backend** — thin FastAPI proxy; your Groq API key stays server-side and is never exposed to the browser

---

## Prerequisites

- **Python 3.10+**
- A free [Groq API key](https://console.groq.com/keys)
- A modern web browser

---

## Quick start

### 1. Clone the repository

```bash
git clone https://github.com/Leonallr10/ad-to-landing-page-fit-analyzer.git
cd ad-to-landing-page-fit-analyzer
```

### 2. Set up the backend

```powershell
cd backend
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment variables

```powershell
copy .env.example .env         # macOS/Linux: cp .env.example .env
```

Edit `backend/.env`:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MAX_TOKENS=1000
GROQ_MAX_LP_CHARS=1500
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | Yes | — | Your Groq API key |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Groq model ID |
| `GROQ_MAX_TOKENS` | No | `1000` | Base output token cap (scales slightly per ad) |
| `GROQ_MAX_LP_CHARS` | No | `1500` | Max landing page characters sent to the model |
| `ALLOWED_ORIGINS` | No | `*` | Comma-separated CORS origins for production |

> **Never commit `backend/.env` to git.** It is listed in `.gitignore`. Use `backend/.env.example` as the template.

### 4. Start the API server

```powershell
cd backend
uvicorn main:app --reload --port 8000
```

Verify the server is running:

```powershell
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "model": "llama-3.3-70b-versatile",
  "key_configured": true
}
```

If `key_configured` is `false`, check your `.env` file and **restart** uvicorn (env changes are not hot-reloaded).

### 5. Open the frontend

Open `frontend/index.html` in your browser (double-click or drag into a tab).

Alternatively, serve it locally:

```powershell
cd frontend
python -m http.server 5500
```

Then visit `http://localhost:5500`.

Set **Backend URL** to `http://localhost:8000`. The status line should show **connected**.

---

## How to use

1. Paste **ad copy** for each variant (use **+ Add another ad** for up to 5 ads).
2. Paste **landing page copy** in the order it appears on the page — hero first.
3. Optionally add the page URL for reference.
4. Click **Run fit analysis**.
5. Review:
   - **Per-ad mismatch report** — dimension scores and gaps
   - **Angle clusters + suggested sections** — tailored hero copy per messaging angle

### Tips for better results

- Put **above-the-fold content at the top** of the landing page paste — continuity is scored against what visitors see first.
- For multi-ad tests, use **clearly different angles** (pain-point vs social proof vs price/urgency).
- Keep landing page paste focused on the first ~1500 characters unless you raise `GROQ_MAX_LP_CHARS`.

---

## Scoring dimensions

Each ad is scored **0–100** per dimension (100 = perfect match, 0 = total mismatch).

| Dimension | What it measures |
|-----------|------------------|
| **Persona fit** | Does the page speak to the same audience the ad implied? |
| **Offer match** | Same specific offer, price, or deal as the ad promised? |
| **Product framing** | Same product/category — or a bait-and-switch? |
| **Proof / evidence** | Does the page back up the ad's claims? |
| **Objection handling** | Does the page address doubts the ad raises? |
| **Above-fold continuity** | Does the top of the page continue the ad's promise immediately? |

Gap notes are shown only for dimensions scoring **below 70** (to reduce noise and token usage).

---

## API reference

### `GET /health`

Health check and configuration status.

**Response**

```json
{
  "status": "ok",
  "model": "llama-3.3-70b-versatile",
  "key_configured": true
}
```

### `POST /analyze`

Run a fit analysis.

**Request body**

```json
{
  "ads": [
    "Headline: Tired of manual invoicing?\nPrimary: AutoInvoice saves 8 hours/week.\nCTA: Try free"
  ],
  "landing_page_url": "https://example.com",
  "landing_page_content": "AutoInvoice — Get paid faster...\n\nSend professional invoices in seconds."
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `ads` | `string[]` | Yes | 1–5 non-empty ad copy blocks |
| `landing_page_content` | `string` | Yes | Min 20 characters |
| `landing_page_url` | `string` | No | Reference only, not fetched |

**Success response** (`200`)

```json
{
  "summary": "Strong persona and offer match; proof is thin above the fold.",
  "ads": [
    {
      "id": 1,
      "cluster": "Pain-point led",
      "dims": {
        "persona": 85,
        "offer": 80,
        "framing": 90,
        "proof": 55,
        "objections": 60,
        "continuity": 75
      },
      "gaps": {
        "persona": "",
        "offer": "",
        "framing": "",
        "proof": "No testimonial in hero",
        "objections": "Migration risk not addressed",
        "continuity": ""
      },
      "fixes": ["Add proof line to hero"],
      "verdict": "Good fit, weak proof"
    }
  ],
  "clusters": [
    {
      "name": "Pain-point led",
      "ad_ids": [1],
      "section": {
        "headline": "Stop Chasing Invoices Manually",
        "subhead": "Send, remind, and get paid in seconds.",
        "proof": "8,000+ freelancers trust AutoInvoice",
        "cta": "Try free"
      }
    }
  ]
}
```

**Error responses**

| Status | Cause |
|--------|-------|
| `400` | All ads empty after trimming |
| `422` | Validation error (e.g. no ads, landing copy too short) |
| `429` | Groq rate limit — wait and retry |
| `500` | `GROQ_API_KEY` missing on server |
| `502` | Groq API unreachable or unparseable response |

**Example (PowerShell)**

```powershell
$body = @{
  ads = @("Headline: Ship projects 2x faster`nCTA: Start free trial")
  landing_page_url = "https://example.com"
  landing_page_content = "TaskFlow — Ship projects 2x faster. Start your free 14-day trial."
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8000/analyze -Method POST -Body $body -ContentType "application/json"
```

---

## Sample test case

**Ad 1 — pain-point angle**

```
Headline: Tired of manual invoicing?
Primary: AutoInvoice sends invoices, chases payments, and syncs with QuickBooks — save 8 hours/week.
CTA: Try free
```

**Ad 2 — social proof angle**

```
Headline: Join 8,000 freelancers who get paid faster
Primary: "I cut my payment time from 30 days to 7" — Sarah K., designer
CTA: See how it works
```

**Landing page copy**

```
AutoInvoice — Get paid faster, automatically

Send professional invoices in seconds. Automatic payment reminders. QuickBooks sync.

"I cut my payment time from 30 days to 7 days." — Sarah K., freelance designer

8,000+ freelancers trust AutoInvoice. 14-day free trial.
```

**Expected:** Two angle clusters (*Pain-point led*, *Social proof led*), per-ad scores, and a suggested hero section for each cluster.

---

## Project structure

```
ad-to-landing-page-fit-analyzer/
├── README.md
├── .gitignore
├── frontend/
│   └── index.html          # Static UI (SIGNAL)
└── backend/
    ├── main.py             # FastAPI app + Groq proxy
    ├── requirements.txt
    ├── .env.example        # Safe template — commit this
    └── .env                # Your secrets — never commit
```

---

## Troubleshooting

### `Server is missing GROQ_API_KEY`

- Confirm `backend/.env` exists and contains `GROQ_API_KEY=...`
- No quotes or spaces around the value
- **Restart uvicorn** after creating or editing `.env`

### `cannot reach backend` in the UI

- Ensure uvicorn is running on port 8000
- Check the Backend URL field matches (`http://localhost:8000`)
- Try `http://127.0.0.1:8000` if `localhost` fails

### GitHub push blocked (secret detected)

- Never commit `backend/.env`
- Rotate the exposed API key at [console.groq.com/keys](https://console.groq.com/keys)
- Ensure `.gitignore` includes `backend/.env`

### Groq rate limit (`429`)

- Wait a few seconds and retry
- Reduce the number of ads in one request
- Lower `GROQ_MAX_TOKENS` in `.env`

### Truncated or incomplete JSON response

- Raise `GROQ_MAX_TOKENS` (e.g. `1200`) for analyses with 3+ ads
- Shorten pasted landing page copy or raise `GROQ_MAX_LP_CHARS`

---

## Limitations

- Does **not** crawl URLs or read images/screenshots
- Does **not** replace A/B testing or real conversion metrics
- Landing page copy is truncated to `GROQ_MAX_LP_CHARS` characters before analysis
- LLM output can vary between runs

---

## License

This project is provided as-is for evaluation and internal marketing QA use.

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Never commit secrets — use `.env.example` only
4. Open a pull request with a clear description of changes
