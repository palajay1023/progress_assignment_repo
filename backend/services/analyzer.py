import asyncio
import json
import logging
from openai import AsyncOpenAI
from backend.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

logger = logging.getLogger(__name__)

ROLE_CONTEXT = {
    "exec": "Focus on strategic implications, market positioning, and high-level business impact.",
    "pm": "Focus on product features, roadmap signals, UX improvements, and competitive feature gaps.",
    "general": "Be thorough and balanced — cover features, strategy, trends, and competitive dynamics.",
}


def _get_client():
    return AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


def _parse_json(text: str) -> dict | list:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    return json.loads(text)


async def map_single_source(
    url: str, extracted_text: str, topics: list[str], role: str
) -> dict | None:
    if not extracted_text or len(extracted_text.strip()) < 50:
        return None

    role_ctx = ROLE_CONTEXT.get(role, ROLE_CONTEXT["general"])
    topics_str = ", ".join(topics) if topics else "general market"
    text_snippet = extracted_text[:12000]

    system_prompt = (
        "You are a market intelligence analyst. Analyze the provided web page content "
        f"for insights related to these topics/competitors: {topics_str}. "
        f"{role_ctx} "
        "Return only valid JSON with no markdown fences."
    )

    user_prompt = f"""Source URL: {url}

Page content:
{text_snippet}

Extract and return a JSON object with exactly this structure:
{{
  "url": "{url}",
  "claims": [
    {{"claim": "...", "source_url": "{url}"}}
  ],
  "competitor_activities": [
    {{"competitor": "...", "activity": "...", "source_url": "{url}"}}
  ],
  "themes_spotted": ["...", "..."]
}}

Rules:
- claims: up to 5 key factual claims from this page (only claims actually present in the text)
- competitor_activities: any competitor actions, launches, or moves mentioned
- themes_spotted: 2-3 high-level themes or patterns you observe
- Every item must have source_url set to exactly "{url}"
- Only include information actually present in the page content
- Return only valid JSON, no markdown"""

    client = _get_client()
    for attempt in range(2):
        try:
            resp = await client.chat.completions.create(
                model=LLM_MODEL,
                max_tokens=1024,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw = resp.choices[0].message.content
            result = _parse_json(raw)
            if not isinstance(result, dict):
                raise ValueError(f"Expected JSON object, got {type(result).__name__}: {raw[:200]}")
            result["url"] = url
            return result
        except Exception as e:
            if attempt == 1:
                logger.warning("map_single_source failed for %s: %s", url, e)
                return None
            await asyncio.sleep(1)

    return None


async def map_all_sources(
    fetch_results: list[dict], topics: list[str], role: str
) -> list[dict]:
    tasks = [
        map_single_source(r["url"], r["extracted_text"], topics, role)
        for r in fetch_results
        if r.get("fetch_status") == "success" and r.get("extracted_text")
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return [r for r in results if r is not None]


async def reduce_all_sources(
    all_map_results: list[dict], topics: list[str], role: str
) -> dict:
    role_ctx = ROLE_CONTEXT.get(role, ROLE_CONTEXT["general"])
    topics_str = ", ".join(topics) if topics else "general market"

    combined = json.dumps(all_map_results, indent=2)
    if len(combined) > 80000:
        combined = combined[:80000] + "\n... (truncated)"

    system_prompt = (
        "You are a senior market intelligence analyst. You will receive structured extracts "
        f"from multiple web sources about these topics: {topics_str}. "
        f"{role_ctx} "
        "Synthesize them into a single comprehensive intelligence report. "
        "Return only valid JSON. No markdown fences."
    )

    user_prompt = f"""Below are structured extracts from {len(all_map_results)} web sources.
Each extract has claims, competitor_activities, and themes_spotted with their source_urls.

SOURCE EXTRACTS:
{combined}

Produce a final intelligence report as JSON with exactly this structure:
{{
  "executive_summary": "2-3 sentence high-level summary of the most important findings",
  "themes": [
    {{
      "title": "Theme title",
      "description": "What this theme means",
      "insights": [
        {{
          "claim": "Specific insight",
          "source_url": "exact URL from the extracts",
          "quote_evidence": "brief supporting quote or paraphrase from the source"
        }}
      ]
    }}
  ],
  "competitor_activities": [
    {{
      "competitor": "Name",
      "activity": "What they did",
      "source_url": "exact URL from the extracts",
      "significance": "Why this matters"
    }}
  ],
  "key_trends": [
    {{
      "trend": "Trend name",
      "description": "What this trend is",
      "source_url": "exact URL from the extracts"
    }}
  ]
}}

Critical rules:
- Every insight, activity, and trend MUST have a source_url copied exactly from the input extracts
- Do NOT invent or hallucinate claims not present in the source extracts
- Return only valid JSON, no markdown fences"""

    client = _get_client()
    for attempt in range(2):
        try:
            resp = await client.chat.completions.create(
                model=LLM_MODEL,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw = resp.choices[0].message.content
            return _parse_json(raw)
        except (json.JSONDecodeError, Exception) as e:
            if attempt == 1:
                raise RuntimeError(f"reduce_all_sources failed after retry: {e}") from e
            await asyncio.sleep(2)

    raise RuntimeError("reduce_all_sources failed")
