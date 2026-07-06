"""
Ad-to-Landing Page Fit Analyzer — backend
------------------------------------------
Thin FastAPI proxy in front of Groq's OpenAI-compatible API.
The Groq key stays server-side; the frontend never sees it.

Run locally:
    pip install -r requirements.txt
    cp .env.example .env   # then paste your real GROQ_API_KEY into .env
    uvicorn main:app --reload --port 8000
"""

import os
import re
import json
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Always load .env from this file's folder (not the shell's cwd).
load_dotenv(Path(__file__).resolve().parent / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fit-analyzer")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_MAX_TOKENS = int(os.environ.get("GROQ_MAX_TOKENS", "1000"))
GROQ_MAX_LP_CHARS = int(os.environ.get("GROQ_MAX_LP_CHARS", "1500"))
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Comma-separated list of allowed origins, e.g. "http://localhost:5500,https://yourapp.com"
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY is not set. /analyze will fail until it is configured in .env")

app = FastAPI(title="Ad-to-Landing Page Fit Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- request / response models ----------

class AnalyzeRequest(BaseModel):
    ads: list[str] = Field(..., min_length=1, max_length=5, description="Ad copy blocks, 1-5 ads")
    landing_page_url: str = Field(default="", description="Reference only, not fetched")
    landing_page_content: str = Field(..., min_length=20, description="Pasted landing page copy, reading order")


# ---------- prompt ----------

SYSTEM_PROMPT = """Marketing analyst: score ad vs landing page on persona, offer, framing, proof, objections, continuity (0-100 each).

Per ad: integer id, 2-4 word angle in "cluster", dims, gaps, 1 fix (max 8 words), verdict (max 6 words).
Gaps: only for dims below 70; else "".
Always return "clusters": group ads by angle; one hero per cluster — headline/subhead/proof/cta, max 8 words each.
summary: 1 short sentence. Integer ids in "id" and "ad_ids" only.

JSON only, no markdown:
{"summary":"","ads":[{"id":1,"cluster":"","dims":{},"gaps":{},"fixes":[""],"verdict":""}],"clusters":[{"name":"","ad_ids":[1],"section":{"headline":"","subhead":"","proof":"","cta":""}}]}"""


def build_user_prompt(req: AnalyzeRequest) -> str:
    ads_block = "\n\n".join(f"AD{i + 1}:\n{ad}" for i, ad in enumerate(req.ads))
    lp = req.landing_page_content.strip()
    if len(lp) > GROQ_MAX_LP_CHARS:
        lp = lp[:GROQ_MAX_LP_CHARS] + "\n...[truncated for analysis]"
    parts = [f"ADS:\n{ads_block}", f"LP:\n{lp}"]
    if req.landing_page_url.strip():
        parts.insert(1, f"URL: {req.landing_page_url.strip()}")
    return "\n\n".join(parts)


def max_output_tokens(ad_count: int) -> int:
    """Scale output cap slightly per ad; keep clusters within a tight budget."""
    return min(GROQ_MAX_TOKENS + (ad_count - 1) * 150, 1400)


def normalize_response(parsed: dict) -> dict:
    """Coerce LLM ids to 1-based integers so the UI labels ads consistently."""
    for i, ad in enumerate(parsed.get("ads") or []):
        raw = ad.get("id", i + 1)
        if isinstance(raw, int):
            ad["id"] = raw
        else:
            m = re.search(r"(\d+)\s*$", str(raw))
            ad["id"] = int(m.group(1)) if m else i + 1

    for cl in parsed.get("clusters") or []:
        normalized: list[int] = []
        for raw in cl.get("ad_ids") or []:
            if isinstance(raw, int):
                normalized.append(raw)
            else:
                m = re.search(r"(\d+)\s*$", str(raw))
                normalized.append(int(m.group(1)) if m else len(normalized) + 1)
        cl["ad_ids"] = normalized

    return parsed


def extract_json(text: str) -> dict:
    """Groq's json_object mode should return clean JSON, but strip fences defensively."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        if t.lower().startswith("json"):
            t = t[4:]
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1:
        t = t[start:end + 1]
    return json.loads(t)


# ---------- routes ----------

@app.get("/health")
async def health():
    return {"status": "ok", "model": GROQ_MODEL, "key_configured": bool(GROQ_API_KEY)}


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="Server is missing GROQ_API_KEY. Set it in .env and restart.")

    ads = [a.strip() for a in req.ads if a.strip()]
    if not ads:
        raise HTTPException(status_code=400, detail="Provide at least one non-empty ad.")

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(req)},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": max_output_tokens(len(ads)),
        "temperature": 0.3,
    }

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.RequestError as e:
        logger.exception("Network error calling Groq")
        raise HTTPException(status_code=502, detail=f"Could not reach Groq API: {e}")

    if r.status_code == 429:
        raise HTTPException(status_code=429, detail="Groq rate limit hit. Wait a moment and try again, or reduce ad count.")
    if r.status_code != 200:
        logger.error("Groq error %s: %s", r.status_code, r.text)
        raise HTTPException(status_code=502, detail=f"Groq API error ({r.status_code}): {r.text[:300]}")

    data = r.json()
    try:
        content = data["choices"][0]["message"]["content"]
        parsed = normalize_response(extract_json(content))
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        logger.error("Could not parse Groq response: %s | raw=%s", e, data)
        raise HTTPException(status_code=502, detail="Groq returned a response that could not be parsed as JSON.")

    return parsed


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)