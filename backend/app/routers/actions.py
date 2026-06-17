from fastapi import APIRouter, HTTPException, Depends, Body
from app.dependencies.auth import get_current_coach_id
from app.services.supabase_client import supabase_service
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Literal
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class ActionUpdateSchema(BaseModel):
    status: Literal["suggested", "accepted", "rejected", "completed"] = Field(
        ..., 
        description="Target status: suggested, accepted, rejected, completed"
    )

@router.patch("/{action_id}")
async def update_action_status(
    action_id: UUID,
    payload: ActionUpdateSchema,
    current_coach_id: str = Depends(get_current_coach_id)
):
    """
    Updates status of a recommended action. 
    Verifies that the action is associated with the authenticated coach.
    """
    db = supabase_service.get_client()
    try:
        # Check action ownership
        action_res = await asyncio.to_thread(
            lambda: db.table("actions")
            .select("coach_id")
            .eq("id", str(action_id))
            .execute()
        )
        
        if not action_res.data:
            raise HTTPException(status_code=404, detail="Action recommendation not found")
            
        action_coach_id = action_res.data[0]["coach_id"]
        if action_coach_id != current_coach_id:
            raise HTTPException(status_code=403, detail="Access denied. You do not own this action.")

        # Update action
        now = datetime.utcnow().isoformat()
        update_res = await asyncio.to_thread(
            lambda: db.table("actions")
            .update({
                "status": payload.status,
                "actioned_by": current_coach_id,
                "actioned_at": now,
                "updated_at": now
            })
            .eq("id", str(action_id))
            .execute()
        )
        
        return update_res.data[0]
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to update action {action_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")
