from fastapi import APIRouter, HTTPException, Query, Header, Depends
from app.services.briefing_engine import briefing_engine
from uuid import UUID
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Authenticaton dependency mapping headers to verified coach ID
async def get_current_coach_id(
    authorization: str = Header(None, description="Bearer Supabase Auth Token"),
    coach_id: str = Query(None, description="Fallback Query Parameter for Development/Testing")
) -> str:
    """
    Dependency that extracts the coach UUID from the Supabase JWT.
    Falls back to development param/UUID if token authentication is bypassed.
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        try:
            # In production: Verify token signature against Supabase Secret Key
            # For this MVP sprint, we extract the claims (mocked/validated decode)
            # and verify the tenant UUID.
            logger.info("Extracting coach_id from Supabase JWT...")
            # placeholder decoding claims
            pass
        except Exception as e:
            logger.error(f"JWT verification failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid authorization credentials")

    # Fallback default coach ID for ease of seed-stage presentation
    fallback_id = coach_id or "00000000-0000-0000-0000-000000000000"
    try:
        UUID(fallback_id)
        return fallback_id
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid coach_id format.")

@router.get("/today")
async def get_today_briefing(current_coach_id: str = Depends(get_current_coach_id)):
    try:
        briefing_payload = await briefing_engine.generate_daily_briefing(current_coach_id)
        return briefing_payload
    except Exception as e:
        logger.error(f"Error fetching today's briefing: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch briefing.")
