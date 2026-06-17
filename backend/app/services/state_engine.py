import asyncio
from typing import Dict, Any
from app.services.supabase_client import supabase_service
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class EntityStateEngine:
    def __init__(self):
        # Checked lazily
        self.db = None

    def _get_db(self):
        if not self.db:
            self.db = supabase_service.get_client()
        return self.db

    async def process_canonical_event(self, event: Dict[str, Any]):
        """
        Updates the entity_state based on the business logic of the canonical event
        and persists the snapshot into entity_snapshots.
        """
        entity_id = event.get('entity_id')
        event_type = event.get('event_type')
        timestamp = event.get('timestamp')
        
        # Determine score deltas
        deltas = {
            'engagement_score': 0,
            'compliance_score': 0,
            'revenue_health': 0
        }
        
        last_checkin = None
        last_payment = None

        if event_type == 'payment_failed':
            deltas['revenue_health'] = -20
            deltas['engagement_score'] = -5
        elif event_type == 'payment_succeeded':
            deltas['revenue_health'] = +10
            last_payment = timestamp
        elif event_type == 'workout_missed':
            deltas['compliance_score'] = -5
            deltas['engagement_score'] = -2
        elif event_type == 'checkin_completed':
            deltas['compliance_score'] = +5
            deltas['engagement_score'] = +5
            last_checkin = timestamp
        elif event_type == 'subscription_cancelled':
            deltas['revenue_health'] = -50
            deltas['engagement_score'] = -20

        # Perform database mutation
        await self._mutate_state(entity_id, deltas, last_checkin, last_payment)

    async def _mutate_state(self, entity_id: str, deltas: Dict[str, int], last_checkin: str | None, last_payment: str | None):
        db = self._get_db()
        try:
            # 1. Fetch current state or insert defaults
            state_res = await asyncio.to_thread(
                lambda: db.table("entity_state").select("*").eq("entity_id", entity_id).execute()
            )
            
            if not state_res.data:
                # Insert initial state
                current_state = {
                    "entity_id": entity_id,
                    "entity_type": "client",
                    "engagement_score": 100,
                    "compliance_score": 100,
                    "revenue_health": 100,
                    "churn_probability": 0.0,
                    "last_checkin": last_checkin,
                    "last_payment": last_payment
                }
                await asyncio.to_thread(
                    lambda: db.table("entity_state").insert(current_state).execute()
                )
            else:
                current_state = state_res.data[0]
                
                # Apply deltas and bound values to [0, 100]
                for key, delta in deltas.items():
                    val = current_state.get(key, 100) + delta
                    current_state[key] = max(0, min(100, val))
                
                if last_checkin:
                    current_state['last_checkin'] = last_checkin
                if last_payment:
                    current_state['last_payment'] = last_payment
                
                current_state['updated_at'] = datetime.utcnow().isoformat()
                
                await asyncio.to_thread(
                    lambda: db.table("entity_state")
                    .update(current_state)
                    .eq("entity_id", entity_id)
                    .execute()
                )

            # 2. Persist to entity_snapshots for audit/temporal tracking
            snapshot = {
                "entity_id": entity_id,
                "date": datetime.utcnow().date().isoformat(),
                "state": {
                    "engagement_score": current_state["engagement_score"],
                    "compliance_score": current_state["compliance_score"],
                    "revenue_health": current_state["revenue_health"],
                    "churn_probability": current_state["churn_probability"]
                }
            }
            # Upsert snapshot for today
            await asyncio.to_thread(
                lambda: db.table("entity_snapshots").upsert(snapshot).execute()
            )

        except Exception as e:
            logger.error(f"Failed to update state engine for entity {entity_id}: {e}")

state_engine = EntityStateEngine()
