import asyncio
import logging
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from app.services.supabase_client import supabase_service
from app.services.identity import identity_service
from app.models.events import CanonicalEvent, EntityType, EventDomain, IntegrationSource

logger = logging.getLogger(__name__)

class TrainerizeAdapter:
    async def process_trainerize_event(self, payload: Dict[str, Any], coach_id: str) -> Optional[Dict[str, Any]]:
        db = supabase_service.get_client()
        external_id = payload.get("event_id")
        
        if not external_id:
            logger.warning("No event_id found in Trainerize payload")
            return None

        # 1. Idempotency Check
        is_duplicate = await asyncio.to_thread(
            lambda: db.table("raw_events")
            .select("id")
            .eq("source", "trainerize")
            .eq("external_id", external_id)
            .execute()
        )
        if is_duplicate.data:
            logger.info(f"Duplicate Trainerize event ignored: {external_id}")
            return None

        # 2. Store Raw Event
        raw_event_insert = await asyncio.to_thread(
            lambda: db.table("raw_events").insert({
                "source": "trainerize",
                "external_id": external_id,
                "payload": payload,
                "coach_id": coach_id,
                "occurred_at": payload.get("timestamp", datetime.utcnow().isoformat())
            }).execute()
        )
        raw_event_id = raw_event_insert.data[0]["id"]

        # 3. Resolve Identity
        client_data = payload.get("client", {})
        email = client_data.get("email")
        name = client_data.get("name", "Unknown Trainerize Client")

        if not email:
            logger.warning(f"No client email found in Trainerize payload {external_id}")
            return None

        person_id = await identity_service.resolve_identity("trainerize", email)
        if not person_id:
            person_id = await identity_service.get_or_create_person(email, name)
            await identity_service.link_identity(person_id, "trainerize", email)

        # Ensure that client relationship is created if it does not already exist
        await asyncio.to_thread(
            lambda: db.table("clients").upsert({
                "person_id": str(person_id),
                "coach_id": coach_id,
                "status": "active"
            }, on_conflict="person_id,coach_id").execute()
        )

        # 4. Map to Canonical Event
        event_type = payload.get("event_type")  # e.g., "workout_completed", "workout_missed"
        canonical_type = "workout_completed"
        if event_type == "workout_missed":
            canonical_type = "workout_missed"

        validation_event = CanonicalEvent(
            coach_id=UUID(coach_id),
            entity_type=EntityType.CLIENT,
            entity_id=UUID(str(person_id)),
            event_domain=EventDomain.COMPLIANCE,
            event_type=canonical_type,
            source=IntegrationSource.TRAINERIZE,
            occurred_at=datetime.utcnow(),
            payload={
                "workout_name": payload.get("workout_name", "Scheduled Workout"),
                "adherence_rate": payload.get("adherence_rate", 1.0)
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

trainerize_adapter = TrainerizeAdapter()
