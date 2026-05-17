import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import uuid
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from backend.database import get_db, init_db
from backend.models import Run, SourceFetch, Claim
from backend.schemas import RunCreate
from backend.services.synthesizer import run_pipeline


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Market Intelligence Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_PATH = Path(__file__).parent.parent / "frontend" / "index.html"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    if FRONTEND_PATH.exists():
        return HTMLResponse(content=FRONTEND_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Frontend not found</h1>", status_code=404)


@app.post("/api/runs")
async def create_run(body: RunCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Parse topics and URLs
    topics = [t.strip() for t in body.topics.split(",") if t.strip()] if body.topics else []
    urls = [u.strip() for u in body.urls.splitlines() if u.strip()] if body.urls else []

    if not topics and not urls:
        raise HTTPException(status_code=400, detail="Provide at least one topic or URL.")

    run_id = str(uuid.uuid4())
    run = Run(
        id=run_id,
        topics=topics,
        urls_provided=urls,
        role=body.role,
        status="pending",
        current_step_detail="Starting...",
    )
    db.add(run)
    db.commit()

    # Run pipeline in background using a fresh DB session
    from backend.database import SessionLocal

    def run_in_background():
        bg_db = SessionLocal()
        # ProactorEventLoop (Windows default) raises "Event loop is closed" during
        # httpx connection cleanup. SelectorEventLoop handles it cleanly.
        if sys.platform == "win32":
            loop = asyncio.SelectorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_pipeline(
                run_id=run_id,
                topics=topics,
                urls_provided=urls,
                role=body.role,
                discover_related=body.discover_related,
                db=bg_db,
            ))
        finally:
            loop.close()
            bg_db.close()

    background_tasks.add_task(run_in_background)

    return {"run_id": run_id}


@app.get("/api/runs/{run_id}/status")
def get_run_status(run_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

    fetches = db.query(SourceFetch).filter(SourceFetch.run_id == run_id).all()
    claims = db.query(Claim).filter(Claim.run_id == run_id).all()

    return {
        "run_id": run.id,
        "status": run.status,
        "current_step_detail": run.current_step_detail,
        "source_fetches": [
            {
                "url": f.url,
                "fetch_status": f.fetch_status,
                "extracted_text_length": f.extracted_text_length,
                "error_message": f.error_message,
            }
            for f in fetches
        ],
        "report_json": run.report_json,
        "claims": [
            {
                "claim": c.claim,
                "source_url": c.source_url,
                "verdict": c.verdict,
                "verdict_reason": c.verdict_reason,
            }
            for c in claims
        ],
        "error_message": run.error_message,
    }


@app.get("/api/runs")
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(Run).order_by(Run.created_at.desc()).limit(50).all()
    return [
        {
            "id": r.id,
            "topics": r.topics or [],
            "role": r.role,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in runs
    ]


if __name__ == "__main__":
    import uvicorn
    print("Starting server → http://localhost:8000")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
