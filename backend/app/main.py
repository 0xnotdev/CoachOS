from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.services.supabase_client import supabase_service
from app.services.feature_store import feature_store_service
from app.services.task_queue import task_queue
from app.utils.logging import setup_logging, request_id_ctx
from app.utils.rate_limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import logging
import uuid

# Initialize structured logging configurations
setup_logging()
logger = logging.getLogger(__name__)

# Initialize Sentry monitoring if configuration key is active
if getattr(settings, "SENTRY_DSN", None):
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=1.0,
    )
    logger.info("Sentry monitoring agent initialized successfully.")

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up CoachOS backend...")
    
    # Verify Supabase configuration on boot
    if supabase_service.client:
        try:
            supabase_service.client.table("raw_events").select("id").limit(1).execute()
            logger.info("Successfully connected to Supabase Database.")
        except Exception as e:
            logger.error(f"Failed to connect to Supabase Database: {e}")
    else:
        logger.warning("Supabase Client not initialized. Running in Mock/Offline mode.")
        
    # Start the SQLite-backed Durable Task Queue worker thread
    await task_queue.start_worker()
    logger.info("Durable SQLite Task Queue worker started.")

    scheduler.add_job(
        feature_store_service.cron_recalculate_time_deltas,
        "interval",
        days=1,
        id="cron_recalculate_time_deltas"
    )
    
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
    await task_queue.stop_worker()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Bind slowapi rate limiter instance
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Enforce secure CORS policy configuration in production
origins = settings.ALLOWED_ORIGINS_LIST
allow_creds = True
if "*" in origins:
    allow_creds = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, 
    allow_credentials=allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_request_id_middleware(request, call_next):
    """
    Middleware injecting unique request-id header mappings across context boundaries.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_ctx.set(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_ctx.reset(token)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": settings.PROJECT_NAME, "version": settings.VERSION}

from app.routers import webhooks, briefing, actions, coaches
app.include_router(webhooks.router, prefix=f"{settings.API_V1_STR}/webhooks", tags=["webhooks"])
app.include_router(briefing.router, prefix=f"{settings.API_V1_STR}/briefing", tags=["briefing"])
app.include_router(actions.router, prefix=f"{settings.API_V1_STR}/actions", tags=["actions"])
app.include_router(coaches.router, prefix=f"{settings.API_V1_STR}/coaches", tags=["coaches"])
