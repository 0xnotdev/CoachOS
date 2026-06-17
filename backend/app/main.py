from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.services.supabase_client import supabase_service
from contextlib import asynccontextmanager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting up CoachOS backend...")
    
    # Verify Supabase connection
    if supabase_service.client:
        try:
            # Quick lightweight query to verify connection
            supabase_service.client.table("raw_events").select("id").limit(1).execute()
            logger.info("Successfully connected to Supabase Database.")
        except Exception as e:
            logger.error(f"Failed to connect to Supabase Database: {e}")
    else:
        logger.warning("Supabase Client not initialized. Running in Mock/Offline mode.")
        
    yield
    
    # Shutdown actions
    logger.info("Shutting down CoachOS backend...")

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

from app.routers import webhooks, briefing
app.include_router(webhooks.router, prefix=f"{settings.API_V1_STR}/webhooks", tags=["webhooks"])
app.include_router(briefing.router, prefix=f"{settings.API_V1_STR}/briefing", tags=["briefing"])
