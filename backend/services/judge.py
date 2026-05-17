import asyncio
import json
from openai import AsyncOpenAI
from backend.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


def _parse_json(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    return json.loads(text)


def _build_source_index(all_map_results: list[dict]) -> dict[str, str]:
    index: dict[str, str] = {}
    for result in all_map_results:
        url = result.get("url", "")
        claims_text = " | ".join(c.get("claim", "") for c in result.get("claims", []))
        activities_text = " | ".join(a.get("activity", "") for a in result.get("competitor_activities", []))
        themes_text = " | ".join(result.get("themes_spotted", []))
        snippet = " ".join(filter(None, [claims_text, activities_text, themes_text]))
        if url:
            index[url] = snippet[:2000]
    return index


def _extract_claims_from_report(summary_json: dict) -> list[dict]:
    items = []
    for theme in summary_json.get("themes", []):
        for insight in theme.get("insights", []):
            if insight.get("claim") and insight.get("source_url"):
                items.append({"claim": insight["claim"], "source_url": insight["source_url"]})
    for activity in summary_json.get("competitor_activities", []):
        if activity.get("activity") and activity.get("source_url"):
            items.append({
                "claim": f"{activity.get('competitor', '')}: {activity['activity']}",
                "source_url": activity["source_url"],
            })
    for trend in summary_json.get("key_trends", []):
        if trend.get("description") and trend.get("source_url"):
            items.append({"claim": trend["description"], "source_url": trend["source_url"]})
    return items


async def run_judge(summary_json: dict, all_map_results: list[dict]) -> list[dict]:
    claims = _extract_claims_from_report(summary_json)
    if not claims:
        return []

    source_index = _build_source_index(all_map_results)
    claims_block = []
    for i, item in enumerate(claims):
        snippet = source_index.get(item["source_url"], "(source snippet not available)")
        claims_block.append(
            f'Claim {i+1}:\n  claim: "{item["claim"]}"\n  source_url: "{item["source_url"]}"\n  source_snippet: "{snippet}"'
        )

    system_prompt = (
        "You are a strict fact-checking judge. Your job is to verify whether each claim "
        "is actually supported by the provided source snippet. "
        "Return only valid JSON — an array. No markdown fences."
    )

    user_prompt = f"""For each claim below, determine whether the source_snippet actually supports it.

{chr(10).join(claims_block)}

Return a JSON array with one object per claim, in the same order:
[
  {{
    "claim": "exact claim text",
    "source_url": "exact source url",
    "verdict": "supported" | "partial" | "unsupported",
    "verdict_reason": "one sentence explaining your verdict"
  }}
]

Verdict definitions:
- supported: the source snippet clearly and directly supports the claim
- partial: the source snippet partially or indirectly supports the claim
- unsupported: the source snippet does not support the claim or the snippet is unavailable

Return only valid JSON array, no markdown."""

    client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

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
            verdicts = _parse_json(raw)
            if not isinstance(verdicts, list):
                raise ValueError("Expected a JSON array")
            return verdicts
        except Exception as e:
            if attempt == 1:
                return [
                    {
                        "claim": item["claim"],
                        "source_url": item["source_url"],
                        "verdict": "unsupported",
                        "verdict_reason": f"Judge failed to evaluate: {e}",
                    }
                    for item in claims
                ]
            await asyncio.sleep(2)

    return []
