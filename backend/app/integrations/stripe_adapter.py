import stripe
import asyncio
from app.config import settings
from app.services.supabase_client import supabase_service
from app.services.identity import identity_service
from app.models.events import CanonicalEvent, EntityType, EventDomain, IntegrationSource
from datetime import datetime
import logging
from typing import Optional, Dict, Any
from uuid import UUID

logger = logging.getLogger(__name__)

class StripeAdapter:
    def __init__(self):
        if not settings.STRIPE_API_KEY:
            logger.warning(
                "STRIPE_API_KEY is not configured in settings. "
                "The server will run with a dummy key for testing/mock integrations."
            )
            stripe.api_key = "sk_test_mock"
        else:
            stripe.api_key = settings.STRIPE_API_KEY

    async def handle_webhook(self, payload: bytes, sig_header: str, coach_id: str, webhook_secret: str) -> Optional[Dict[str, Any]]:
        """
        Parses webhook with the coach-specific signature secret and triggers pipeline logic.
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
            return await self.process_stripe_event(event, coach_id)
        except ValueError as e:
            logger.error("Invalid Stripe payload")
            raise e
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Signature verification failed for coach {coach_id}")
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
            logger.info(f"Duplicate Stripe event ignored: {external_id}")
            return None

        # 2. Store Raw Event
        raw_event_insert = await asyncio.to_thread(
            lambda: db.table("raw_events").insert({
                "source": "stripe",
                "external_id": external_id,
                "payload": stripe_event,
                "coach_id": coach_id,
                "occurred_at": datetime.fromtimestamp(stripe_event.get("created", datetime.utcnow().timestamp())).isoformat()
            }).execute()
        )
        raw_event_id = raw_event_insert.data[0]["id"]
        
        # ... Rest of client resolution ...
        data_object = stripe_event.get("data", {}).get("object", {})
        customer_id = data_object.get("customer")
        
        if not customer_id:
            logger.warning(f"No customer ID in event {external_id}")
            return None

        person_id = await identity_service.resolve_identity("stripe", customer_id)
        
        if not person_id:
            coach_res = await asyncio.to_thread(
                lambda: db.table("coaches")
                .select("stripe_connected_account_id")
                .eq("id", coach_id)
                .execute()
            )
            connected_account_id = None
            if coach_res.data:
                connected_account_id = coach_res.data[0].get("stripe_connected_account_id")

            email = data_object.get("customer_email") or data_object.get("email")
            if not email and settings.STRIPE_API_KEY:
                try:
                    customer = await asyncio.to_thread(
                        lambda: stripe.Customer.retrieve(
                            customer_id, 
                            stripe_account=connected_account_id
                        ) if connected_account_id else stripe.Customer.retrieve(customer_id)
                    )
                    email = customer.get("email")
                except Exception as e:
                    logger.error(f"Failed to retrieve customer {customer_id} for Connect Account {connected_account_id}: {e}")

            if not email:
                email = f"unresolved_{customer_id}@coachos.internal"
                logger.warning(f"Defaulting email for Stripe customer {customer_id}")

            name = data_object.get("customer_name") or "Unknown Stripe Client"
            person_id = await identity_service.get_or_create_person(email, name)
            await identity_service.link_identity(person_id, "stripe", customer_id)

        # Ensure that client relationship is created if it does not already exist
        await asyncio.to_thread(
            lambda: db.table("clients").upsert({
                "person_id": str(person_id),
                "coach_id": coach_id,
                "status": "active"
            }, on_conflict="person_id,coach_id").execute()
        )

        # 4. Map and Normalize to Canonical Event
        event_type = stripe_event.get("type")
        canonical_type = "payment_unknown"
        
        amount = data_object.get("amount") or data_object.get("amount_due") or 0
        currency = data_object.get("currency") or "usd"
        reason = data_object.get("failure_reason") or data_object.get("reason") or "unknown"
        
        structured_payload = {
            "amount": amount / 100.0,
            "currency": currency.upper(),
            "reason": reason
        }

        if event_type == "invoice.payment_failed":
            canonical_type = "payment_failed"
        elif event_type == "invoice.payment_succeeded":
            canonical_type = "payment_succeeded"
        elif event_type == "customer.subscription.deleted":
            canonical_type = "subscription_cancelled"

        # 5. Enforce Canonical Schema Contract validation in Python.
        validation_event = CanonicalEvent(
            coach_id=UUID(coach_id),
            entity_type=EntityType.CLIENT,
            entity_id=UUID(str(person_id)),
            event_domain=EventDomain.REVENUE,
            event_type=canonical_type,
            source=IntegrationSource.STRIPE,
            occurred_at=datetime.fromtimestamp(stripe_event.get("created")),
            payload=structured_payload
        )

        # 6. Save to Database
        canonical_insert = await asyncio.to_thread(
            lambda: db.table("canonical_events").insert({
                "id": str(validation_event.event_id),
                "coach_id": str(validation_event.coach_id),
                "entity_type": validation_event.entity_type.value,
                "entity_id": str(validation_event.entity_id),
                "event_domain": validation_event.event_domain.value,
                "event_type": validation_event.event_type,
                "timestamp": validation_event.occurred_at.isoformat(),
                "structured_payload": validation_event.payload,
                "raw_event_id": str(raw_event_id)
            }).execute()
        )

        
        return canonical_insert.data[0]

# Global singleton instantiated on module load (raises if config is missing)
stripe_adapter = StripeAdapter()
