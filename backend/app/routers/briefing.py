from fastapi import APIRouter, HTTPException, Header, Depends
from app.services.briefing_engine import briefing_engine
from app.services.supabase_client import supabase_service
from app.config import settings
from uuid import UUID
import jwt
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

async def get_current_coach_id(
    authorization: str = Header(None, description="Bearer Supabase Auth Token")
) -> str:
    """
    Decodes and validates the Supabase JWT.
    Enforces strict token validation and resolves to coaches.auth_user_id.
    """
    if not authorization:
        logger.warning("Unauthenticated request blocked. Missing Authorization header.")
        raise HTTPException(status_code=401, detail="Authentication credentials required. Please provide a Bearer JWT.")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format. Must start with 'Bearer '")

    token = authorization.split(" ")[1]
    
    jwt_secret = settings.SUPABASE_JWT_SECRET
    if not jwt_secret:
        logger.critical("SUPABASE_JWT_SECRET is not configured in settings. Auth verification blocked.")
        raise HTTPException(status_code=500, detail="Authentication service configuration error.")

    try:
        decoded_payload = jwt.decode(
            token, 
            jwt_secret, 
            algorithms=["HS256"], 
            options={"verify_aud": False, "verify_signature": True}
        )
        user_id = decoded_payload.get("sub")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Subject claim missing from token claims")
            
        db = supabase_service.get_client()
        coach_res = await asyncio.to_thread(
            lambda: db.table("coaches")
            .select("id")
            .eq("auth_user_id", user_id)
            .execute()
        )
        
        if not coach_res.data:
            logger.error(f"No Coach entity links to authenticated user ID {user_id}")
            raise HTTPException(status_code=403, detail="Authenticated user is not registered as a coach")
            
        return coach_res.data[0]["id"]

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Authentication token has expired")
    except jwt.InvalidTokenError as e:
        logger.error(f"JWT Decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid auth token signature")
    except Exception as e:
        logger.error(f"Authentication processing error: {e}")
        raise HTTPException(status_code=500, detail="Authentication server error")

@router.get("/today")
async def get_today_briefing(current_coach_id: str = Depends(get_current_coach_id)):
    try:
        briefing_payload = await briefing_engine.generate_daily_briefing(current_coach_id)
        return briefing_payload
    except Exception as e:
        logger.error(f"Error fetching today's briefing: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch briefing.")

@router.get("/clients")
async def get_coach_clients(current_coach_id: str = Depends(get_current_coach_id)):
    """
    Returns all clients under the authenticated coach joined with state and feature metrics.
    """
    db = supabase_service.get_client()
    try:
        clients_res = await asyncio.to_thread(
            lambda: db.table("clients")
            .select("id, person_id, status")
            .eq("coach_id", current_coach_id)
            .execute()
        )
        
        if not clients_res.data:
            return []

        client_records = clients_res.data
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
