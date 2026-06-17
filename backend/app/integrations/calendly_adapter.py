import asyncio
import logging
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from app.services.supabase_client import supabase_service
from app.services.identity import identity_service
from app.models.events import CanonicalEvent, EntityType, EventDomain, IntegrationSource

logger = logging.getLogger(__name__)

class CalendlyAdapter:
    async def process_calendly_event(self, payload: Dict[str, Any], coach_id: str) -> Optional[Dict[str, Any]]:
        db = supabase_service.get_client()
        external_id = payload.get("event_uuid") or payload.get("uri", "").split("/")[-1]
        
        if not external_id:
            logger.warning("No external ID found in Calendly payload")
            return None

        # 1. Idempotency Check
        is_duplicate = await asyncio.to_thread(
            lambda: db.table("raw_events")
            .select("id")
            .eq("source", "calendly")
            .eq("external_id", external_id)
            .execute()
        )
        if is_duplicate.data:
            logger.info(f"Duplicate Calendly event ignored: {external_id}")
            return None

        # 2. Store Raw Event
        raw_event_insert = await asyncio.to_thread(
            lambda: db.table("raw_events").insert({
                "source": "calendly",
                "external_id": external_id,
                "payload": payload,
                "coach_id": coach_id,
                "occurred_at": payload.get("timestamp", datetime.utcnow().isoformat())
            }).execute()
        )
        raw_event_id = raw_event_insert.data[0]["id"]

        # 3. Resolve Identity from Invitee Details
        invitee_data = payload.get("invitee", {})
        email = invitee_data.get("email")
        name = invitee_data.get("name", "Unknown Calendly Invitee")

        if not email:
            logger.warning(f"No invitee email in Calendly event {external_id}")
            return None

        person_id = await identity_service.resolve_identity("calendly", email)
        if not person_id:
            person_id = await identity_service.get_or_create_person(email, name)
            await identity_service.link_identity(person_id, "calendly", email)

        # Ensure that client relationship is created if it does not already exist
        await asyncio.to_thread(
            lambda: db.table("clients").upsert({
                "person_id": str(person_id),
                "coach_id": coach_id,
                "status": "active"
            }, on_conflict="person_id,coach_id").execute()
        )

        # 4. Map to Canonical Event
        event_name = payload.get("event") or "invitee.created"
        canonical_type = "session_scheduled"
        if event_name == "invitee.cancelled":
            canonical_type = "session_cancelled"

        validation_event = CanonicalEvent(
            coach_id=UUID(coach_id),
            entity_type=EntityType.CLIENT,
            entity_id=UUID(str(person_id)),
            event_domain=EventDomain.SCHEDULING,
            event_type=canonical_type,
            source=IntegrationSource.CALENDLY,
            occurred_at=datetime.utcnow(),
            payload={
                "event_type_name": payload.get("event_type_name", "Coaching Session"),
                "start_time": payload.get("start_time"),
                "cancel_reason": payload.get("cancel_reason", "")
            }
        )

        # 5. Save to Database
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

calendly_adapter = CalendlyAdapter()
