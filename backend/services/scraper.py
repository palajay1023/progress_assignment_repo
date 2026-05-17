import asyncio
import json
import httpx
import trafilatura
from backend.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, TAVILY_API_KEY

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
FETCH_TIMEOUT = 15
MIN_TEXT_LENGTH = 500
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


async def fetch_and_extract(url: str) -> dict:
    """Fetch a URL and extract its text content. Returns {url, extracted_text, fetch_status}."""
    base = {"url": url, "extracted_text": "", "fetch_status": "failed"}

    try:
        # Step 1 — PDF detection
        if url.lower().endswith(".pdf"):
            return await _extract_pdf(url, base)

        # Step 2 — Fetch raw HTML
        async with httpx.AsyncClient(follow_redirects=True, timeout=FETCH_TIMEOUT) as client:
            try:
                resp = await client.get(url, headers={"User-Agent": USER_AGENT})
            except (httpx.TimeoutException, httpx.RequestError) as e:
                base["error_message"] = str(e)
                return base

            content_type = resp.headers.get("content-type", "")
            if "application/pdf" in content_type:
                return await _extract_pdf(url, base, content=resp.content)

            html = resp.text

        # Step 3 — trafilatura
        text = trafilatura.extract(html, include_comments=False, include_tables=True)
        if text and len(text) > MIN_TEXT_LENGTH:
            base["extracted_text"] = text
            base["fetch_status"] = "success"
            return base

        # Step 4 — Tavily Extract fallback
        return await _tavily_extract(url, base)

    except Exception as e:
        base["error_message"] = str(e)
        return base


async def _extract_pdf(url: str, base: dict, content: bytes = None) -> dict:
    try:
        import fitz  # PyMuPDF

        if content is None:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers={"User-Agent": USER_AGENT})
                content = resp.content

        doc = fitz.open(stream=content, filetype="pdf")
        pages = [page.get_text() for page in doc]
        text = "\n".join(pages).strip()
        doc.close()

        if not text:
            base["fetch_status"] = "scanned_pdf"
            return base

        base["extracted_text"] = text
        base["fetch_status"] = "success"
        return base
    except Exception as e:
        base["error_message"] = str(e)
        return base


async def _tavily_extract(url: str, base: dict) -> dict:
    if not TAVILY_API_KEY:
        return base
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                TAVILY_EXTRACT_URL,
                json={"urls": [url]},
                headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
            )
            data = resp.json()
            results = data.get("results", [])
            if results:
                text = results[0].get("raw_content", "")
                if text and len(text) > MIN_TEXT_LENGTH:
                    base["extracted_text"] = text
                    base["fetch_status"] = "success"
                    return base
    except Exception as e:
        base["error_message"] = str(e)
    return base


async def discover_urls(topic: str) -> list[str]:
    """Generate search queries via Claude, run them through Tavily Search, return deduplicated URLs."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    # Step 1 — Ask Claude for 3 targeted search queries
    system_prompt = (
        "You are a market research assistant. Given a competitor or topic name, "
        "return exactly 3 targeted search queries to find recent news, product updates, "
        "blog posts, announcements, and changelogs about that topic. "
        "Return only valid JSON — an array of 3 strings. No markdown fences."
    )
    user_prompt = f'Topic: "{topic}"\n\nReturn a JSON array of 3 search queries.'

    queries = []
    try:
        resp = await client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=256,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        queries = json.loads(raw)
        if not isinstance(queries, list):
            queries = [f"{topic} product updates 2025", f"{topic} announcements", f"{topic} changelog"]
    except Exception:
        queries = [f"{topic} product updates 2025", f"{topic} announcements", f"{topic} changelog"]

    # Step 2 — Run each query through Tavily Search
    all_urls: list[str] = []
    if not TAVILY_API_KEY:
        return all_urls

    async def search_one(query: str) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    TAVILY_SEARCH_URL,
                    json={"query": query, "search_depth": "basic", "max_results": 5, "include_videos": False},
                    headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
                )
                data = resp.json()
                return [r["url"] for r in data.get("results", []) if "url" in r]
        except Exception:
            return []

    results = await asyncio.gather(*[search_one(q) for q in queries])
    for urls in results:
        all_urls.extend(urls)

    # Step 3 — Deduplicate and cap at 15
    seen: set[str] = set()
    deduped: list[str] = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
        if len(deduped) >= 15:
            break

    return deduped
