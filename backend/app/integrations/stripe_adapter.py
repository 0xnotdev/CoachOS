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

    async def handle_webhook(self, payload: bytes, sig_header: str) -> Optional[Dict[str, Any]]:
        """
        Parses webhook and triggers normalization, persistence, and identity resolution.
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_secret
            )
            return await self.process_stripe_event(event)
        except ValueError as e:
            logger.error("Invalid Stripe payload")
            raise e
        except stripe.error.SignatureVerificationError as e:
            logger.error("Invalid Stripe signature")
            raise e

    async def process_stripe_event(self, stripe_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
        
        # Identity Fallback / Creation
        if not person_id:
            # Try to fetch customer details to get email for fuzzy matching
            email = data_object.get("customer_email") or data_object.get("email")
            if not email and settings.STRIPE_API_KEY:
                try:
                    customer = await asyncio.to_thread(stripe.Customer.retrieve, customer_id)
                    email = customer.get("email")
                except Exception as e:
                    logger.error(f"Failed to fetch Stripe customer: {e}")

            if email:
                # Fuzzy match in persons table
                match = await asyncio.to_thread(
                    lambda: db.table("persons").select("id").eq("email", email).execute()
                )
                if match.data:
                    person_id = UUID(match.data[0]["id"])
                    await identity_service.link_identity(person_id, "stripe", customer_id)

            # Still no person? Create a new person record
            if not person_id:
                name = data_object.get("customer_name") or "Unknown Stripe Client"
                new_person = await asyncio.to_thread(
                    lambda: db.table("persons").insert({"name": name, "email": email}).execute()
                )
                person_id = UUID(new_person.data[0]["id"])
                await identity_service.link_identity(person_id, "stripe", customer_id)

        # 4. Map and Normalize to Canonical Event
        event_type = stripe_event.get("type")
        canonical_type = "payment_unknown"
        domain = "revenue"

        if event_type == "invoice.payment_failed":
            canonical_type = "payment_failed"
        elif event_type == "invoice.payment_succeeded":
            canonical_type = "payment_succeeded"
        elif event_type == "customer.subscription.deleted":
            canonical_type = "subscription_cancelled"

        # Save Canonical Event
        canonical_insert = await asyncio.to_thread(
            lambda: db.table("canonical_events").insert({
                "entity_type": "client",
                "entity_id": str(person_id),
                "event_domain": domain,
                "event_type": canonical_type,
                "timestamp": datetime.fromtimestamp(stripe_event.get("created")).isoformat(),
                "raw_event_id": raw_event_id
            }).execute()
        )
        
        return canonical_insert.data[0]

stripe_adapter = StripeAdapter()
