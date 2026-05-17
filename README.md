# Market Research Intelligence Assistant

A web application that collects, analyzes, and summarizes competitor activity and market trends from public sources — with source-grounded insights and LLM-as-a-judge hallucination verification.

**Live demo:** https://web-production-80676.up.railway.app/

---

## Problem Statement

Product and GTM teams need to stay current on competitor activity and market trends, but relevant signals are scattered across blogs, announcement pages, press releases, and articles. Manually tracking these sources is time-consuming and inconsistent. This application lets a user provide a list of topics or competitors plus a set of source URLs, then automatically fetches, analyzes, and synthesizes the content into a structured intelligence report — with every insight traceable back to the URL it came from, and every claim fact-checked against the source material.

---

## Architecture & Tech Stack

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser (React SPA)                  │
│  InputForm → ProgressView (polling) → ReportView            │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP (REST)
┌──────────────────────▼──────────────────────────────────────┐
│                   FastAPI  (backend/main.py)                 │
│  POST /api/runs  ·  GET /api/runs/{id}/status  ·  GET /api/runs │
└──┬────────────────────────────────────────────────────────┬─┘
   │ background task                                        │
   ▼                                                        ▼
┌──────────────────────────┐              ┌─────────────────────┐
│  Pipeline Orchestrator   │              │  SQLite (SQLAlchemy) │
│  (services/synthesizer)  │◄────────────►│  Run · SourceFetch  │
│                          │              │  Claim tables        │
│  1. Discover URLs        │              └─────────────────────┘
│  2. Fetch Content        │
│  3. Map (per-source LLM) │◄──── OpenAI-compatible LLM API
│  4. Reduce (report LLM)  │◄──── (gpt-4o / claude-sonnet / etc.)
│  5. Judge (fact-check)   │
│  6. Finalize             │
└──────┬───────────────────┘
       │
       ├── scraper.py   → trafilatura · PyMuPDF · Tavily Extract API
       ├── analyzer.py  → LLM map + reduce (JSON-mode)
       └── judge.py     → LLM-as-a-judge verdict generation
```

### Tech Stack

| Layer | Technology |
|---|---|
| **Backend framework** | [FastAPI](https://fastapi.tiangolo.com/) 0.111+ |
| **ASGI server** | [Uvicorn](https://www.uvicorn.org/) |
| **Database ORM** | [SQLAlchemy](https://www.sqlalchemy.org/) 2.0 + SQLite |
| **HTTP client** | [httpx](https://www.python-httpx.org/) (async) |
| **HTML extraction** | [trafilatura](https://trafilatura.readthedocs.io/) |
| **PDF extraction** | [PyMuPDF](https://pymupdf.readthedocs.io/) (fitz) |
| **Web search & extract** | [Tavily API](https://tavily.com/) |
| **LLM client** | [openai](https://github.com/openai/openai-python) SDK (provider-agnostic) |
| **Frontend** | React 18 via CDN (no build step), Babel in-browser transpile |
| **Deployment** | [Railway](https://railway.app/) via Nixpacks |
| **Runtime** | Python 3.11.9 |

---

## Local Build & Run Instructions

### Prerequisites

- Python 3.11+
- An LLM API key (OpenAI, Anthropic via OpenRouter, or any OpenAI-compatible provider)
- A [Tavily API key](https://tavily.com/) (free tier available) for URL discovery

### Steps

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd market_summary

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 3. Install Python dependencies
pip install -r backend/requirements.txt

# 4. Configure environment variables
copy .env.example .env     # Windows
cp .env.example .env       # macOS / Linux

# Edit .env and fill in your keys:
# LLM_API_KEY=sk-...
# LLM_BASE_URL=https://api.openai.com/v1   (or your provider's base URL)
# LLM_MODEL=gpt-4o                         (or claude-sonnet-4-20250514, etc.)
# TAVILY_API_KEY=tvly-...
# DATABASE_URL=sqlite:///./market_intelligence.db

# 5. Start the server
python -m uvicorn backend.main:app --reload

# 6. Open the app
# http://localhost:8000
```

### Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `LLM_API_KEY` | Yes | API key for your LLM provider |
| `LLM_BASE_URL` | No | OpenAI-compatible base URL (default: `https://api.openai.com/v1`) |
| `LLM_MODEL` | No | Model ID (default: `gpt-4o`) |
| `TAVILY_API_KEY` | Yes | Tavily Search + Extract API key |
| `DATABASE_URL` | No | SQLAlchemy DB URL (default: `sqlite:///./market_intelligence.db`) |

> **Backward-compatible aliases:** `OPENROUTER_API_KEY` maps to `LLM_API_KEY`; `CLAUDE_MODEL` maps to `LLM_MODEL`.

### Using Anthropic Claude directly (via OpenRouter)

```env
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=<your-openrouter-key>
LLM_MODEL=anthropic/claude-sonnet-4-20250514
```

---

## Deploy to Railway

1. Push this repo to GitHub.
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub** → select this repo.
3. Add environment variables in the Railway dashboard: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `TAVILY_API_KEY`.
4. Railway builds via Nixpacks and starts the server automatically (`python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT`).
5. Railway provides a public HTTPS URL on deploy.

---

## AI Tools, Models & Libraries Used

### Language Model

| Component | Model | Purpose |
|---|---|---|
| URL query generation | Configurable (default `gpt-4o`) | Generate 3 focused search queries per topic |
| Map (per-source) | Configurable (default `gpt-4o`) | Extract claims, competitor activities, themes from each page |
| Reduce (synthesis) | Configurable (default `gpt-4o`) | Synthesize all source analyses into structured report |
| Judge (fact-check) | Configurable (default `gpt-4o`) | Verdict each claim as supported / partial / unsupported |

The app uses the **OpenAI Python SDK** in provider-agnostic mode — point `LLM_BASE_URL` at any OpenAI-compatible endpoint (OpenAI, Anthropic via OpenRouter, Together AI, Groq, local Ollama, etc.) without changing any code.

### Web Search & Content Extraction

- **[Tavily Search API](https://tavily.com/)** — Retrieves ranked URLs for each AI-generated query. Chosen over raw Google/Bing scraping because it returns clean, deduplicated results without needing API quota management. ([docs](https://docs.tavily.com/))
- **[Tavily Extract API](https://tavily.com/)** — Fallback content extractor for pages where trafilatura returns less than 500 characters (JavaScript-heavy or paywalled pages).
- **[trafilatura](https://trafilatura.readthedocs.io/)** — Primary HTML-to-text extractor. Handles boilerplate removal, encoding issues, and partial content — significantly cleaner output than raw BeautifulSoup parsing.
- **[PyMuPDF (fitz)](https://pymupdf.readthedocs.io/)** — PDF text extraction. Detects scanned (image-only) PDFs by checking character count vs. page count.

### LLM-as-a-Judge (Hallucination Detection)

The `judge.py` service implements the **LLM-as-a-judge** pattern described in [Zheng et al., 2023 — "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena"](https://arxiv.org/abs/2306.05685). Each claim in the final report is re-evaluated by the LLM against the raw source snippet it came from, returning one of three verdicts:

- **supported** — the source text clearly supports the claim
- **partial** — the source provides indirect or incomplete support
- **unsupported** — no supporting evidence found in the source

---

## Design Decisions

### 1. Map-Reduce LLM Pipeline

Rather than feeding all source text into a single large prompt (which would exceed context limits at scale), the pipeline uses a **map-reduce** architecture:

- **Map phase:** Each successfully fetched URL is analyzed independently by the LLM, producing a structured JSON of claims, competitor activities, and themes — each with a `source_url` field. This caps per-call cost and allows parallel execution.
- **Reduce phase:** All map outputs are concatenated and passed to a single synthesis call that produces the final structured report. Input is capped at 80,000 characters to stay within model context windows.

This pattern scales to 10–20 URLs without hitting context limits and makes retries cheap (only re-run failed individual pages).

### 2. Provider-Agnostic LLM Client

The codebase uses the OpenAI Python SDK's `base_url` parameter rather than the Anthropic SDK directly. This lets the same code work with OpenAI, Anthropic (via OpenRouter), Together AI, Groq, or a local Ollama instance by changing two environment variables — no code changes needed. This was chosen to keep the app deployable in environments where only certain API keys are available.

### 3. No Frontend Build Step

The frontend is a single `index.html` file using React 18 and Babel loaded from CDN. This eliminates Node.js, npm, and a build pipeline from the deployment requirements — FastAPI serves the file directly, Railway only needs Python. The tradeoff is slightly slower initial load (Babel transpiles JSX in-browser) and no tree-shaking, which is acceptable for an internal tool at this scale.

### 4. Role-Based Prompting

Three analyst personas are supported via system prompt variation:
- **General** — balanced coverage across all findings
- **PM** — emphasizes feature signals, roadmap gaps, and competitive positioning
- **Exec** — focuses on strategic implications, market share signals, and business impact

The LLM receives the same source content each time; only the system prompt changes. This lets one run cover multiple audiences without re-fetching or re-scraping.

### 5. Hallucination Verification as a First-Class Step

Fact-checking is built into the pipeline (step 5 of 6), not offered as an optional add-on. Every claim in the report is checked before the run is marked `completed`. Verdicts are stored in the database and displayed inline with each insight in the UI. This gives reviewers a quick signal of confidence without needing to manually cross-reference sources.

### 6. Graceful Degradation

The pipeline continues if individual URLs fail to fetch — partial results are better than no results. If the judge step fails for a claim, it defaults to `unsupported` rather than crashing. If the reduce step returns malformed JSON, the error is captured and the run is marked `failed` with a descriptive message. This makes the app robust to flaky external sources.

### 7. Persistent Run History

SQLite stores every run, source fetch result, and claim verdict. The sidebar shows the last 50 runs so users can revisit and compare analyses over time without re-running. This also provides an audit trail: what URLs were fetched, which succeeded or failed, and what the model concluded.

---

## Project Structure

```
market_summary/
├── backend/
│   ├── main.py              # FastAPI app, routes, background task dispatch
│   ├── config.py            # Environment variable loading
│   ├── database.py          # SQLAlchemy engine + session
│   ├── models.py            # DB models: Run, SourceFetch, Claim
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── requirements.txt
│   └── services/
│       ├── synthesizer.py   # 6-step pipeline orchestrator
│       ├── scraper.py       # Content fetching + URL discovery
│       ├── analyzer.py      # LLM map (per-source) + reduce (report)
│       └── judge.py         # LLM-as-a-judge fact-checking
├── frontend/
│   └── index.html           # Single-file React 18 SPA (no build step)
├── .env.example
├── railway.json
├── nixpacks.toml
├── Procfile
└── runtime.txt              # Python 3.11.9
```

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |
| `GET` | `/` | Serves the frontend |
| `POST` | `/api/runs` | Start a new analysis run |
| `GET` | `/api/runs/{run_id}/status` | Poll run status, fetches, and report |
| `GET` | `/api/runs` | List last 50 runs |

### POST /api/runs — Request Body

```json
{
  "topics": "Notion, Linear",
  "urls": "https://example.com/blog\nhttps://example.com/news",
  "role": "general",
  "discover_related": true
}
```

### GET /api/runs/{id}/status — Response

```json
{
  "run_id": "...",
  "status": "completed",
  "current_step_detail": "Run complete. 4 of 5 URLs fetched successfully.",
  "source_fetches": [
    { "url": "https://...", "fetch_status": "success", "extracted_text_length": 5200 }
  ],
  "report_json": {
    "executive_summary": "...",
    "themes": [...],
    "competitor_activities": [...],
    "key_trends": [...]
  },
  "claims": [
    { "claim": "...", "source_url": "...", "verdict": "supported", "verdict_reason": "..." }
  ]
}
```
