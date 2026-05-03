import warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from routes.rules import router as rules_router
from routes.upload import router as upload_router
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import os

load_dotenv()

app = FastAPI(
    title="MedinspectAI",
    description="Pharmaceutical packaging compliance checker",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rules_router)
app.include_router(upload_router)

# ── SCHEDULER ───────────────────────────────────────────
scheduler = AsyncIOScheduler()

async def auto_refresh_rules():
    """Runs every 30 days — refreshes stale rules automatically."""
    print("\n[Scheduler] 🔄 Auto rule refresh triggered...")
    try:
        from run_extraction import run
        await run()
        print("[Scheduler] ✅ Auto refresh complete!")
    except Exception as e:
        print(f"[Scheduler] ❌ Auto refresh failed: {e}")

@app.on_event("startup")
async def startup():
    scheduler.add_job(
        auto_refresh_rules,
        trigger=IntervalTrigger(days=30),
        id="rule_refresh",
        name="Auto Rule Refresh",
        replace_existing=True
    )
    scheduler.start()
    print("[Scheduler] ✅ Auto rule refresh scheduled every 30 days")

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()
    print("[Scheduler] Stopped")

# ── ROUTES ──────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "MedinspectAI backend running ✅"}

@app.get("/health")
def health():
    job = scheduler.get_job("rule_refresh")
    return {
        "status":       "ok",
        "markets":      os.getenv("SUPPORTED_MARKETS", "").split(","),
        "next_refresh": str(job.next_run_time) if job else "not scheduled"
    }

@app.get("/refresh-rules")
async def manual_refresh():
    """Manually trigger rule refresh from browser/API."""
    print("[Manual] Rule refresh triggered via API...")
    await auto_refresh_rules()
    return {"status": "Rules refreshed ✅"}