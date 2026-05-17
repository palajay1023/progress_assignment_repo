import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.models import Run, SourceFetch, Claim
from backend.services.scraper import fetch_and_extract, discover_urls
from backend.services.analyzer import map_all_sources, reduce_all_sources
from backend.services.judge import run_judge

logger = logging.getLogger(__name__)


def _update_run(db: Session, run_id: str, **kwargs):
    run = db.query(Run).filter(Run.id == run_id).first()
    if run:
        for k, v in kwargs.items():
            setattr(run, k, v)
        run.updated_at = datetime.now(timezone.utc)
        db.commit()


def _save_source_fetch(db: Session, run_id: str, result: dict):
    sf = SourceFetch(
        run_id=run_id,
        url=result["url"],
        fetch_status=result.get("fetch_status", "failed"),
        extracted_text_length=len(result.get("extracted_text", "")),
        error_message=result.get("error_message"),
    )
    db.add(sf)
    db.commit()


def _save_claims(db: Session, run_id: str, verdicts: list[dict]):
    for v in verdicts:
        db.add(Claim(
            run_id=run_id,
            claim=v.get("claim", ""),
            source_url=v.get("source_url", ""),
            verdict=v.get("verdict", "unsupported"),
            verdict_reason=v.get("verdict_reason", ""),
        ))
    db.commit()


def _attach_verdicts_to_report(report: dict, verdicts: list[dict]) -> dict:
    verdict_map = {
        (v.get("claim", ""), v.get("source_url", "")): v
        for v in verdicts
    }

    for theme in report.get("themes", []):
        for insight in theme.get("insights", []):
            v = verdict_map.get((insight.get("claim", ""), insight.get("source_url", "")))
            insight["verdict"] = v["verdict"] if v else "unsupported"
            insight["verdict_reason"] = v["verdict_reason"] if v else ""

    for activity in report.get("competitor_activities", []):
        key = (f"{activity.get('competitor', '')}: {activity.get('activity', '')}", activity.get("source_url", ""))
        v = verdict_map.get(key)
        activity["verdict"] = v["verdict"] if v else "unsupported"
        activity["verdict_reason"] = v["verdict_reason"] if v else ""

    for trend in report.get("key_trends", []):
        v = verdict_map.get((trend.get("description", ""), trend.get("source_url", "")))
        trend["verdict"] = v["verdict"] if v else "unsupported"
        trend["verdict_reason"] = v["verdict_reason"] if v else ""

    return report


async def run_pipeline(
    run_id: str,
    topics: list[str],
    urls_provided: list[str],
    role: str,
    discover_related: bool,
    db: Session,
):
    try:
        # ── Step 1: Collect URLs ─────────────────────────────────────────────
        _update_run(db, run_id, status="discovering_urls",
                    current_step_detail="Collecting URLs...")

        all_urls: set[str] = set(urls_provided)

        if topics:
            # Always discover for topics — that's the only way to get URLs for them
            results = await asyncio.gather(*[discover_urls(t) for t in topics])
            for url_list in results:
                all_urls.update(url_list)
        elif urls_provided and discover_related:
            # User provided URLs and wants extra — use URL domains as search context
            results = await asyncio.gather(*[discover_urls(u) for u in urls_provided[:3]])
            for url_list in results:
                all_urls.update(url_list)

        if urls_provided and discover_related and topics:
            # Both provided + discovery wanted — already handled above (topics discovered)
            pass

        url_list = list(all_urls)
        _update_run(db, run_id, current_step_detail=f"Found {len(url_list)} URLs to analyze.")

        # ── Step 2: Fetch content ────────────────────────────────────────────
        _update_run(db, run_id, status="fetching_content",
                    current_step_detail=f"Fetching {len(url_list)} URLs...")

        fetch_results = list(await asyncio.gather(*[fetch_and_extract(u) for u in url_list]))
        for r in fetch_results:
            _save_source_fetch(db, run_id, r)

        successful = [r for r in fetch_results if r.get("fetch_status") == "success"]

        if len(successful) < 1:
            _update_run(db, run_id, status="failed",
                        error_message=(
                            f"0 of {len(url_list)} URLs yielded usable content. "
                            f"Try different URLs or enable link discovery."
                        ))
            return

        _update_run(db, run_id,
                    current_step_detail=f"Extracted content from {len(successful)} of {len(url_list)} URLs.")

        # ── Step 3: Map — analyze each source in parallel ────────────────────
        _update_run(db, run_id, status="analyzing_sources",
                    current_step_detail=f"Analyzing {len(successful)} sources...")

        map_results = await map_all_sources(successful, topics, role)
        if not map_results:
            _update_run(db, run_id, status="failed",
                        error_message=(
                            f"LLM analysis returned no results for any of the {len(successful)} fetched sources. "
                            f"Check your LLM_API_KEY and LLM_MODEL in .env, then check the server logs for details."
                        ))
            return

        # ── Step 4: Reduce — synthesize final report ─────────────────────────
        _update_run(db, run_id, status="generating_report",
                    current_step_detail="Synthesizing intelligence report...")

        report = await reduce_all_sources(map_results, topics, role)

        # ── Step 5: Judge — verify claims ────────────────────────────────────
        _update_run(db, run_id, status="verifying_claims",
                    current_step_detail="Verifying claims against sources...")

        verdicts = await run_judge(report, map_results)
        _save_claims(db, run_id, verdicts)

        # ── Step 6: Finalize ─────────────────────────────────────────────────
        report = _attach_verdicts_to_report(report, verdicts)
        report["_meta"] = {
            "total_urls": len(url_list),
            "successful_urls": len(successful),
            "failed_urls": [
                {"url": r["url"], "reason": r.get("fetch_status", "failed")}
                for r in fetch_results if r.get("fetch_status") != "success"
            ],
        }

        _update_run(db, run_id, status="completed",
                    current_step_detail="Report complete.", report_json=report)

    except Exception as e:
        logger.exception("Pipeline failed for run %s", run_id)
        _update_run(db, run_id, status="failed", error_message=str(e))
