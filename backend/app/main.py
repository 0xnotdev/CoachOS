from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.services.supabase_client import supabase_service
from app.services.feature_store import feature_store_service
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up CoachOS backend...")
    
    if supabase_service.client:
        try:
            supabase_service.client.table("raw_events").select("id").limit(1).execute()
            logger.info("Successfully connected to Supabase Database.")
        except Exception as e:
            logger.error(f"Failed to connect to Supabase Database: {e}")
    else:
        logger.warning("Supabase Client not initialized. Running in Mock/Offline mode.")
        
    scheduler.add_job(
        feature_store_service.cron_recalculate_time_deltas,
        "interval",
        days=1,
        id="cron_recalculate_time_deltas"
    )
    
    # Schedule cron to run asynchronously 30 seconds after server startup,
    # preventing server block and health check drop failures under load.
    scheduler.add_job(
        feature_store_service.cron_recalculate_time_deltas,
        "date",
        run_date=datetime.now() + timedelta(seconds=30),
        id="initial_recalculate_time_deltas"
    )
    
    scheduler.start()
    logger.info("APScheduler initialized: Daily cron scheduled (with 30s deferred initial run).")
    
    yield
    
    logger.info("Shutting down CoachOS backend...")
    scheduler.shutdown()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Enforce secure CORS policy configuration in production
origins = settings.ALLOWED_ORIGINS_LIST
allow_creds = True
if "*" in origins:
    allow_creds = False # Browser spec blocks credential transfer on wildcard origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, 
    allow_credentials=allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": settings.PROJECT_NAME, "version": settings.VERSION}

from app.routers import webhooks, briefing, actions, coaches
app.include_router(webhooks.router, prefix=f"{settings.API_V1_STR}/webhooks", tags=["webhooks"])
app.include_router(briefing.router, prefix=f"{settings.API_V1_STR}/briefing", tags=["briefing"])
app.include_router(actions.router, prefix=f"{settings.API_V1_STR}/actions", tags=["actions"])
app.include_router(coaches.router, prefix=f"{settings.API_V1_STR}/coaches", tags=["coaches"])
