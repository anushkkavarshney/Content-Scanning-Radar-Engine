from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
import os

from src.trend_engine import generate_trends, fetch_trends
from src.scheduler import start_scheduler
from src.mongo_client import get_db

app = FastAPI(title="AI Trend Detection Engine")

# Simple CORS - configure via env in production
origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("trend_engine")
logging.basicConfig(level=logging.INFO)

@app.on_event("startup")
def on_startup():
    if os.getenv("SCHEDULE_ENABLED", "false").lower() in ("1","true","yes"):
        start_scheduler()

@app.post("/generate_trends")
def api_generate_trends():
    """Trigger trend generation from current news_articles."""
    trends = generate_trends()
    return JSONResponse({"success": True, "data": trends, "meta": {}})

@app.get("/trends")
def api_get_trends():
    """Return generated trends sorted by trend_score desc."""
    trends = fetch_trends()
    return JSONResponse({"success": True, "data": trends, "meta": {}})

@app.get('/health')
def health():
    """Health check: database connectivity and article count"""
    try:
        db = get_db()
        count = db[os.getenv('ARTICLES_COLLECTION','news_articles')].count_documents({})
        return JSONResponse({"success": True, "data": {"db": True, "articles": count}})
    except Exception as e:
        logger.exception('Health check failed')
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
