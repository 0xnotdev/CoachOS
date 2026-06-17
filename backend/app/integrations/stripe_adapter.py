import stripe
from app.config import settings
from app.models.events import CanonicalEvent, EntityType, EventDomain, IntegrationSource, EventMetadata
from datetime import datetime
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_API_KEY

class StripeAdapter:
    def __init__(self):
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    async def handle_webhook(self, payload: bytes, sig_header: str) -> Optional[CanonicalEvent]:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_secret
            )
            return await self.normalize_event(event)
        except ValueError as e:
            logger.error("Invalid Stripe payload")
            raise e
        except stripe.error.SignatureVerificationError as e:
            logger.error("Invalid Stripe signature")
            raise e

    async def normalize_event(self, stripe_event: Dict[str, Any]) -> Optional[CanonicalEvent]:
        """Convert a Stripe event into a CanonicalEvent"""
        
        event_type = stripe_event.get("type")
        data_object = stripe_event.get("data", {}).get("object", {})
        
        # Simple mapping for Phase 1
        domain = EventDomain.REVENUE
        
        # We need a way to resolve the Stripe customer to our Client entity
        # For now, we'll use a placeholder UUID, but in reality this uses the EntityResolver
        from uuid import uuid4
        mock_coach_id = uuid4()
        mock_client_id = uuid4()

        if event_type.startswith("payment_intent."):
            pass # Handle payment intent events
        elif event_type.startswith("customer.subscription."):
            pass # Handle subscription events

        canonical_event = CanonicalEvent(
            coach_id=mock_coach_id,
            entity_type=EntityType.CLIENT,
            entity_id=mock_client_id,
            event_domain=domain,
            event_type=f"stripe.{event_type}",
            source=IntegrationSource.STRIPE,
            occurred_at=datetime.fromtimestamp(stripe_event.get("created", datetime.utcnow().timestamp())),
            payload=data_object,
            metadata=EventMetadata(
                original_event_id=stripe_event.get("id"),
                dedup_key=f"stripe_{stripe_event.get('id')}"
            )
        )
        
        return canonical_event

stripe_adapter = StripeAdapter()
