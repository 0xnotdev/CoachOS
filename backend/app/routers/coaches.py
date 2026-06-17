from fastapi import APIRouter, HTTPException, Header, Body
from app.services.supabase_client import supabase_service
from app.config import settings
from pydantic import BaseModel, EmailStr
from uuid import UUID, uuid4
import jwt
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class CoachRegisterRequest(BaseModel):
    name: str
    email: EmailStr
    business_tier: str = "free"
    stripe_connected_account_id: str | None = None
    stripe_webhook_secret: str | None = None

@router.post("/register")
async def register_new_coach(
    payload: CoachRegisterRequest,
    authorization: str = Header(None, description="Bearer Supabase Auth Token")
):
    """
    Onboards a brand new coach using their Supabase JWT.
    Corrects identity collisions by decoupling auth_user_id from persons.id.
    Includes full recovery path to re-provision missing webhook endpoints on retry.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication credentials required. Please provide a Bearer JWT.")

    token = authorization.split(" ")[1]
    jwt_secret = settings.SUPABASE_JWT_SECRET
    
    if not jwt_secret:
        logger.critical("SUPABASE_JWT_SECRET is not configured.")
        raise HTTPException(status_code=500, detail="Authentication configuration missing on server.")

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

        # 1. Check if coach already registered under this auth_user_id
        existing_coach = await asyncio.to_thread(
            lambda: db.table("coaches")
            .select("id, person_id")
            .eq("auth_user_id", user_id)
            .execute()
        )
        
        if existing_coach.data:
            coach_id = existing_coach.data[0]["id"]
            
            # Recovery path: Fetch existing webhook endpoint
            endpoint_res = await asyncio.to_thread(
                lambda: db.table("webhook_endpoints")
                .select("webhook_token")
                .eq("coach_id", coach_id)
                .execute()
            )
            
            if not endpoint_res.data:
                # Provision missing webhook endpoint on retry
                webhook_token = str(uuid4())
                await asyncio.to_thread(
                    lambda: db.table("webhook_endpoints").insert({
                        "webhook_token": webhook_token,
                        "coach_id": coach_id,
                        "stripe_webhook_secret": payload.stripe_webhook_secret
                    }).execute()
                )
                logger.info(f"Recovered and provisioned missing webhook endpoint for coach {coach_id}")
            else:
                webhook_token = endpoint_res.data[0]['webhook_token']

            webhook_url = f"{settings.API_V1_STR}/webhooks/stripe/{webhook_token}"
            
            return {
                "message": "Coach already registered.",
                "coach_id": coach_id,
                "webhook_url": webhook_url
            }

        # 2. Check if a person record exists for this email
        person_res = await asyncio.to_thread(
            lambda: db.table("persons")
            .select("id")
            .eq("email", payload.email)
            .execute()
        )
        
        if person_res.data:
            # Reuses existing cross-system identity record, preventing email collision errors
            person_id = person_res.data[0]["id"]
        else:
            # Create a new person record with a unique uuid
            new_person = await asyncio.to_thread(
                lambda: db.table("persons").insert({
                    "id": str(uuid4()),
                    "name": payload.name,
                    "email": payload.email
                }).execute()
            )
            person_id = new_person.data[0]["id"]

        # 3. Create the coaches record, binding auth_user_id to user_id (auth.uid())
        new_coach = await asyncio.to_thread(
            lambda: db.table("coaches").insert({
                "person_id": person_id,
                "auth_user_id": user_id,
                "business_tier": payload.business_tier,
                "stripe_connected_account_id": payload.stripe_connected_account_id
            }).execute()
        )
        coach_id = new_coach.data[0]["id"]

        # 4. Generate the webhook endpoint mapping
        webhook_token = str(uuid4())
        await asyncio.to_thread(
            lambda: db.table("webhook_endpoints").insert({
                "webhook_token": webhook_token,
                "coach_id": coach_id,
                "stripe_webhook_secret": payload.stripe_webhook_secret
            }).execute()
        )

        webhook_url = f"{settings.API_V1_STR}/webhooks/stripe/{webhook_token}"

        return {
            "message": "Coach successfully onboarded.",
            "coach_id": coach_id,
            "webhook_url": webhook_url
        }

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Authentication token has expired")
    except jwt.InvalidTokenError as e:
        logger.error(f"JWT Decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token signature")
    except Exception as e:
        logger.error(f"Failed to provision coach: {e}")
        raise HTTPException(status_code=500, detail="Provisioning process failed")
