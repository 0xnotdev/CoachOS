import stripe
import asyncio
from app.config import settings
from app.services.supabase_client import supabase_service
from app.services.identity import identity_service
from datetime import datetime
import logging
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_API_KEY

class StripeAdapter:
    def __init__(self):
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    async def handle_webhook(self, payload: bytes, sig_header: str, coach_id: str) -> Optional[Dict[str, Any]]:
        """
        Parses webhook and triggers normalization, persistence, and identity resolution.
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_secret
            )
            return await self.process_stripe_event(event, coach_id)
        except ValueError as e:
            logger.error("Invalid Stripe payload")
            raise e
        except stripe.error.SignatureVerificationError as e:
            logger.error("Invalid Stripe signature")
            raise e

    async def process_stripe_event(self, stripe_event: Dict[str, Any], coach_id: str) -> Optional[Dict[str, Any]]:
        db = supabase_service.get_client()
        external_id = stripe_event.get("id")
        
        # 1. Idempotency Check
        is_duplicate = await asyncio.to_thread(
            lambda: db.table("raw_events")
            .select("id")
            .eq("source", "stripe")
            .eq("external_id", external_id)
            .execute()
        )
        if is_duplicate.data:
            logger.info(f"Duplicate Stripe event detected and ignored: {external_id}")
            return None

        # 2. Store Raw Event
        raw_event_insert = await asyncio.to_thread(
            lambda: db.table("raw_events").insert({
                "source": "stripe",
                "external_id": external_id,
                "payload": stripe_event,
                "occurred_at": datetime.fromtimestamp(stripe_event.get("created", datetime.utcnow().timestamp())).isoformat()
            }).execute()
        )
        raw_event_id = raw_event_insert.data[0]["id"]

        # 3. Resolve Identity
        data_object = stripe_event.get("data", {}).get("object", {})
        customer_id = data_object.get("customer")
        
        if not customer_id:
            logger.warning(f"No customer ID associated with event {external_id}")
            return None

        person_id = await identity_service.resolve_identity("stripe", customer_id)
        
        # Fallback & atomic identity resolution
        if not person_id:
            email = data_object.get("customer_email") or data_object.get("email")
            if not email and settings.STRIPE_API_KEY:
                try:
                    customer = await asyncio.to_thread(stripe.Customer.retrieve, customer_id)
                    email = customer.get("email")
                except Exception as e:
                    logger.error(f"Failed to fetch Stripe customer details: {e}")

            if not email:
                # If email is totally unrecoverable, we insert a placeholder record for manual audit
                email = f"unresolved_{customer_id}@coachos.internal"
                logger.warning(f"Unable to retrieve client email for Stripe customer {customer_id}. Queueing for manual resolution.")

            # Race-condition-guarded atomic client retrieval/creation
            name = data_object.get("customer_name") or "Unknown Stripe Client"
            person_id = await identity_service.get_or_create_person(email, name)
            await identity_service.link_identity(person_id, "stripe", customer_id)

        # 4. Map and Normalize to Canonical Event
        event_type = stripe_event.get("type")
        canonical_type = "payment_unknown"
        domain = "revenue"
        
        # Extract structured payload contexts
        amount = data_object.get("amount") or data_object.get("amount_due") or 0
        currency = data_object.get("currency") or "usd"
        reason = data_object.get("failure_reason") or data_object.get("reason") or "unknown"
        
        structured_payload = {
            "amount": amount / 100.0, # Convert cents to standard float decimal
            "currency": currency.upper(),
            "reason": reason
        }

        if event_type == "invoice.payment_failed":
            canonical_type = "payment_failed"
        elif event_type == "invoice.payment_succeeded":
            canonical_type = "payment_succeeded"
        elif event_type == "customer.subscription.deleted":
            canonical_type = "subscription_cancelled"

        # Save Canonical Event (including structured payload for downstream feature logic)
        canonical_insert = await asyncio.to_thread(
            lambda: db.table("canonical_events").insert({
                "entity_type": "client",
                "entity_id": str(person_id),
                "event_domain": domain,
                "event_type": canonical_type,
                "timestamp": datetime.fromtimestamp(stripe_event.get("created")).isoformat(),
                "structured_payload": structured_payload,
                "raw_event_id": raw_event_id
            }).execute()
        )
        
        return canonical_insert.data[0]

stripe_adapter = StripeAdapter()
