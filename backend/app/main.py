from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.services.supabase_client import supabase_service
from app.services.feature_store import feature_store_service
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize background scheduler for time-delta recalculations
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting up CoachOS backend...")
    
    # Verify Supabase connection
    if supabase_service.client:
        try:
            supabase_service.client.table("raw_events").select("id").limit(1).execute()
            logger.info("Successfully connected to Supabase Database.")
        except Exception as e:
            logger.error(f"Failed to connect to Supabase Database: {e}")
    else:
        logger.warning("Supabase Client not initialized. Running in Mock/Offline mode.")
        
    # Schedule feature time-delta recalculations to run daily
    scheduler.add_job(
        feature_store_service.cron_recalculate_time_deltas,
        "interval",
        days=1,
        id="cron_recalculate_time_deltas"
    )
    scheduler.start()
    logger.info("APScheduler initialized: Registered daily feature store recalculation job.")
    
    # Run the cron once immediately on startup to refresh stale counts
    await feature_store_service.cron_recalculate_time_deltas()
    
    yield
    
    # Shutdown actions
    logger.info("Shutting down CoachOS backend...")
    scheduler.shutdown()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Set all CORS enabled origins - restrict for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": settings.PROJECT_NAME, "version": settings.VERSION}

from app.routers import webhooks, briefing, actions
app.include_router(webhooks.router, prefix=f"{settings.API_V1_STR}/webhooks", tags=["webhooks"])
app.include_router(briefing.router, prefix=f"{settings.API_V1_STR}/briefing", tags=["briefing"])
app.include_router(actions.router, prefix=f"{settings.API_V1_STR}/actions", tags=["actions"])
