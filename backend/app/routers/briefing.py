from fastapi import APIRouter, HTTPException, Depends, Request
from app.services.briefing_engine import briefing_engine
from app.services.supabase_client import supabase_service
from app.dependencies.auth import get_current_coach_id
from app.utils.rate_limiter import limiter
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/today")
@limiter.limit("5/minute")
async def get_today_briefing(
    request: Request,
    current_coach_id: str = Depends(get_current_coach_id)
):
    try:
        briefing_payload = await briefing_engine.generate_daily_briefing(current_coach_id)
        return briefing_payload
    except Exception as e:
        logger.error(f"Error fetching today's briefing: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch briefing.")

@router.get("/clients")
@limiter.limit("10/minute")
async def get_coach_clients(
    request: Request,
    current_coach_id: str = Depends(get_current_coach_id)
):
    """
    Returns all clients under the authenticated coach joined with state and feature metrics.
    Correctly paginates queries via .range() limit boundaries to scale past database defaults.
    """
    db = supabase_service.get_client()
    try:
        client_records = []
        page_size = 100
        start = 0
        has_more = True
        
        while has_more:
            end = start + page_size - 1
            clients_res = await asyncio.to_thread(
                lambda: db.table("clients")
                .select("id, person_id, status")
                .eq("coach_id", current_coach_id)
                .range(start, end)
                .execute()
            )
            
            if not clients_res.data:
                break
                
            client_records.extend(clients_res.data)
            
            if len(clients_res.data) < page_size:
                has_more = False
            else:
                start += page_size

        if not client_records:
            return []

        person_ids = [c["person_id"] for c in client_records]

        persons_task = asyncio.to_thread(
            lambda: db.table("persons").select("id, name, email").in_("id", person_ids).execute()
        )
        states_task = asyncio.to_thread(
            lambda: db.table("entity_state").select("*").in_("entity_id", person_ids).execute()
        )
        features_task = asyncio.to_thread(
            lambda: db.table("feature_store").select("*").in_("entity_id", person_ids).execute()
        )

        p_res, s_res, f_res = await asyncio.gather(persons_task, states_task, features_task)

        persons_map = {row["id"]: row for row in (p_res.data or [])}
        states_map = {row["entity_id"]: row for row in (s_res.data or [])}
        features_map = {row["entity_id"]: row for row in (f_res.data or [])}

        clients_list = []
        for client in client_records:
            pid = client["person_id"]
            person = persons_map.get(pid, {})
            state = states_map.get(pid, {})
            features = features_map.get(pid, {})

            clients_list.append({
                "client_id": client["id"],
                "person_id": pid,
                "name": person.get("name", "Unknown Client"),
                "email": person.get("email", ""),
                "status": client["status"],
                "engagement_score": state.get("engagement_score", 100),
                "compliance_score": state.get("compliance_score", 100),
                "revenue_health": state.get("revenue_health", 100),
                "churn_probability": state.get("churn_probability", 0.0),
                "days_since_checkin": features.get("days_since_checkin", 0),
                "days_since_payment": features.get("days_since_payment", 0)
            })

        return clients_list

    except Exception as e:
        logger.error(f"Error fetching coach clients list: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve client roster.")
