import asyncio
import logging
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from app.services.supabase_client import supabase_service
from app.services.identity import identity_service
from app.models.events import CanonicalEvent, EntityType, EventDomain, IntegrationSource

logger = logging.getLogger(__name__)

class TypeformAdapter:
    async def process_typeform_event(self, payload: Dict[str, Any], coach_id: str) -> Optional[Dict[str, Any]]:
        db = supabase_service.get_client()
        form_response = payload.get("form_response", {})
        external_id = form_response.get("token")
        
        if not external_id:
            logger.warning("No response token found in Typeform payload")
            return None

        # 1. Idempotency Check
        is_duplicate = await asyncio.to_thread(
            lambda: db.table("raw_events")
            .select("id")
            .eq("source", "typeform")
            .eq("external_id", external_id)
            .execute()
        )
        if is_duplicate.data:
            logger.info(f"Duplicate Typeform event ignored: {external_id}")
            return None

        # 2. Store Raw Event
        raw_event_insert = await asyncio.to_thread(
            lambda: db.table("raw_events").insert({
                "source": "typeform",
                "external_id": external_id,
                "payload": payload,
                "coach_id": coach_id,
                "occurred_at": form_response.get("submitted_at", datetime.utcnow().isoformat())
            }).execute()
        )
        raw_event_id = raw_event_insert.data[0]["id"]

        # 3. Resolve Identity from Form Response Answers
        # Typically, a Typeform has an email field or hidden field with email
        email = None
        name = "Unknown Typeform Client"
        
        # Look for email in hidden fields
        hidden_fields = form_response.get("hidden", {})
        email = hidden_fields.get("email")
        
        # fallback: loop through answers to find email and weight if present
        answers = form_response.get("answers", [])
        extracted_weight = None

        for answer in answers:
            a_type = answer.get("type")
            field_ref = answer.get("field", {}).get("ref", "")
            
            if a_type == "email":
                email = answer.get("email")
            elif "weight" in field_ref.lower():
                extracted_weight = answer.get("number") or answer.get("text")

        if not email:
            logger.warning(f"Could not resolve client email in Typeform response {external_id}")
            return None

        person_id = await identity_service.resolve_identity("typeform", email)
        if not person_id:
            person_id = await identity_service.get_or_create_person(email, name)
            await identity_service.link_identity(person_id, "typeform", email)

        # Ensure that client relationship is created if it does not already exist
        await asyncio.to_thread(
            lambda: db.table("clients").upsert({
                "person_id": str(person_id),
                "coach_id": coach_id,
                "status": "active"
            }, on_conflict="person_id,coach_id").execute()
        )

        # 4. Map to Canonical Event
        event_ref = form_response.get("form_id", "weekly_checkin")
        canonical_type = "checkin_completed"
        
        event_payload = {
            "form_id": form_response.get("form_id"),
            "title": form_response.get("definition", {}).get("title", "Weekly Check-in Form")
        }
        if extracted_weight:
            try:
                event_payload["weight"] = float(extracted_weight)
            except ValueError:
                pass

        validation_event = CanonicalEvent(
            coach_id=UUID(coach_id),
            entity_type=EntityType.CLIENT,
            entity_id=UUID(str(person_id)),
            event_domain=EventDomain.COMPLIANCE,
            event_type=canonical_type,
            source=IntegrationSource.TYPEFORM,
            occurred_at=datetime.utcnow(),
            payload=event_payload
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

typeform_adapter = TypeformAdapter()
