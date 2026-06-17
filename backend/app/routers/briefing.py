from fastapi import APIRouter, HTTPException, Query
from app.services.briefing_engine import briefing_engine
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/today")
async def get_today_briefing(coach_id: str = Query(..., description="The UUID of the coach requesting the briefing")):
    try:
        # Call the briefing engine to construct the briefing
        briefing_content = await briefing_engine.generate_daily_briefing(coach_id)
        return {"briefing": briefing_content}
    except Exception as e:
        logger.error(f"Error fetching today's briefing: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch briefing.")
