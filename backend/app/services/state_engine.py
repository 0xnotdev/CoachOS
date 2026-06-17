import asyncio
from typing import Dict, Any
from app.services.supabase_client import supabase_service
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class EntityStateEngine:
    def __init__(self):
        self.db = None

    def _get_db(self):
        if not self.db:
            self.db = supabase_service.get_client()
        return self.db

    async def process_canonical_event(self, event: Dict[str, Any]):
        """
        Updates the entity_state based on event logic and persists the snapshot.
        Enforces intelligent state recovery (e.g. successful payment fully resets revenue health).
        """
        entity_id = event.get('entity_id')
        event_type = event.get('event_type')
        timestamp = event.get('timestamp')
        
        deltas = {
            'engagement_score': 0,
            'compliance_score': 0,
            'revenue_health': 0
        }
        
        overrides = {}
        last_checkin = None
        last_payment = None

        if event_type == 'payment_failed':
            deltas['revenue_health'] = -20
            deltas['engagement_score'] = -5
        elif event_type == 'payment_succeeded':
            overrides['revenue_health'] = 100
            deltas['engagement_score'] = +10
            last_payment = timestamp
        elif event_type == 'workout_missed':
            deltas['compliance_score'] = -5
            deltas['engagement_score'] = -2
        elif event_type == 'checkin_completed':
            deltas['compliance_score'] = +15
            deltas['engagement_score'] = +10
            last_checkin = timestamp
        elif event_type == 'subscription_cancelled':
            overrides['revenue_health'] = 0
            deltas['engagement_score'] = -30

        await self._mutate_state(entity_id, deltas, overrides, last_checkin, last_payment)

    async def _mutate_state(self, entity_id: str, deltas: Dict[str, int], overrides: Dict[str, int], last_checkin: str | None, last_payment: str | None):
        db = self._get_db()
        try:
            # Call atomic PL/pgSQL function to update scores inside the DB, preventing race conditions
            await asyncio.to_thread(
                lambda: db.rpc("mutate_entity_state", {
                    "p_entity_id": entity_id,
                    "p_entity_type": "client",
                    "p_engagement_delta": deltas.get("engagement_score", 0),
                    "p_compliance_delta": deltas.get("compliance_score", 0),
                    "p_revenue_delta": deltas.get("revenue_health", 0),
                    "p_engagement_override": overrides.get("engagement_score"),
                    "p_compliance_override": overrides.get("compliance_score"),
                    "p_revenue_override": overrides.get("revenue_health"),
                    "p_last_checkin": last_checkin,
                    "p_last_payment": last_payment
                }).execute()
            )

            # Query updated state to ensure accurate snapshots
            updated_res = await asyncio.to_thread(
                lambda: db.table("entity_state").select("*").eq("entity_id", entity_id).execute()
            )
            
            if updated_res.data:
                current_state = updated_res.data[0]
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
                await asyncio.to_thread(
                    lambda: db.table("entity_snapshots").upsert(snapshot).execute()
                )

        except Exception as e:
            logger.error(f"Failed to update state engine for entity {entity_id}: {e}")

state_engine = EntityStateEngine()
