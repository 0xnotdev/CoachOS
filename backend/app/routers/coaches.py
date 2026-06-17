from fastapi import APIRouter, HTTPException, Depends, Body
from app.services.supabase_client import supabase_service
from app.dependencies.auth import get_current_user_id, get_current_coach_id
from app.config import settings
from app.utils.security import security_helper
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID, uuid4
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class CoachRegisterRequest(BaseModel):
    name: str
    email: EmailStr
    business_tier: str = "free"
    stripe_connected_account_id: str | None = None

class StripeIntegrationUpdateRequest(BaseModel):
    stripe_webhook_secret: str = Field(
        ..., 
        description="Write-only Stripe webhook signature secret to decrypt events securely"
    )

@router.post("/register")
async def register_new_coach(
    payload: CoachRegisterRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Onboards a brand new coach using their Supabase JWT.
    Corrects identity collisions by decoupling auth_user_id from persons.id.
    Includes full recovery path to re-provision missing webhook endpoints on retry.
    Credentials (webhook secrets) are excluded from registration payloads for logging security.
    """
    # Trim and lowercase email to enforce consistent identity keys
    normalized_email = payload.email.strip().lower()

    try:
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
                # Provision missing webhook endpoint on retry (webhook secret is set separately via PATCH)
                webhook_token = str(uuid4())
                await asyncio.to_thread(
                    lambda: db.table("webhook_endpoints").insert({
                        "webhook_token": webhook_token,
                        "coach_id": coach_id,
                        "stripe_webhook_secret": None
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
            .eq("email", normalized_email)
            .execute()
        )
        
        if person_res.data:
            person_id = person_res.data[0]["id"]
        else:
            # Create a new person record with a unique uuid
            new_person = await asyncio.to_thread(
                lambda: db.table("persons").insert({
                    "id": str(uuid4()),
                    "name": payload.name,
                    "email": normalized_email
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
                "stripe_webhook_secret": None
            }).execute()
        )

        webhook_url = f"{settings.API_V1_STR}/webhooks/stripe/{webhook_token}"

        return {
            "message": "Coach successfully onboarded.",
            "coach_id": coach_id,
            "webhook_url": webhook_url
        }

    except Exception as e:
        logger.error(f"Failed to provision coach: {e}")
        raise HTTPException(status_code=500, detail="Provisioning process failed")

@router.patch("/integrations/stripe")
async def update_stripe_credentials(
    payload: StripeIntegrationUpdateRequest,
    current_coach_id: str = Depends(get_current_coach_id)
):
    """
    Securely uploads and encrypts integration credentials (stripe_webhook_secret) at rest.
    """
    db = supabase_service.get_client()
    try:
        # Encrypt Stripe webhook signature secret before database insertion
        encrypted_secret = security_helper.encrypt(payload.stripe_webhook_secret)

        update_res = await asyncio.to_thread(
            lambda: db.table("webhook_endpoints")
            .update({"stripe_webhook_secret": encrypted_secret})
            .eq("coach_id", current_coach_id)
            .execute()
        )
        
        if not update_res.data:
            raise HTTPException(
                status_code=404, 
                detail="Webhook endpoint configuration mapping not found for coach integration"
            )
            
        return {
            "status": "success",
            "message": "Stripe webhook signature credentials encrypted and updated successfully."
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to secure Stripe credentials: {e}")
        raise HTTPException(status_code=500, detail="Credential encryption update failed")
