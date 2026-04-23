from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from routes.rules import router as rules_router
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

@app.get("/")
def root():
    return {"status": "MedinspectAI backend running ✅"}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "markets": os.getenv("SUPPORTED_MARKETS").split(",")
    }