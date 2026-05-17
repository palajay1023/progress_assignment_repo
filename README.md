# Market Intelligence Assistant

A web app that collects, analyzes, and summarizes competitor activity and market trends from public sources using Claude AI.

## Features

- Provide competitor names/topics and/or source URLs
- Optionally discover additional related links via Tavily Search
- AI-generated report: themes, competitor activities, key trends
- Source traceability — every insight links back to its URL
- Hallucination checking via LLM-as-a-judge (supported / partial / unsupported)
- Persistent run history

## Local Setup

```bash
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # macOS/Linux

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Set environment variables
cp .env.example .env
# Edit .env and add your API keys

# 4. Run the app
uvicorn backend.main:app --reload

# 5. Open http://localhost:8000
```

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (required) |
| `TAVILY_API_KEY` | Tavily API key (required for URL discovery) |
| `DATABASE_URL` | SQLite path (default: `sqlite:///./market_intelligence.db`) |

## Deploy to Railway

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select this repo
4. Add environment variables: `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `DATABASE_URL`
5. Railway auto-deploys and provides a live HTTPS URL

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, SQLite
- **Frontend**: React (CDN, no build step)
- **AI**: Anthropic Claude (`claude-sonnet-4-20250514`)
- **Fetching**: httpx, trafilatura, PyMuPDF, Tavily Extract
- **Discovery**: Tavily Search API
