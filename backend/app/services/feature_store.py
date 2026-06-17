import asyncio
from typing import Dict, Any
from app.services.supabase_client import supabase_service
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class FeatureStoreService:
    def __init__(self):
        self.db = None

    def _get_db(self):
        if not self.db:
            self.db = supabase_service.get_client()
        return self.db

    async def update_features(self, entity_id: str, new_event: Dict[str, Any]):
        """
        Recalculates rolling aggregates for the entity and updates the feature_store table.
        """
        db = self._get_db()
        try:
            event_type = new_event.get("event_type")
            
            # Fetch current features
            feat_res = await asyncio.to_thread(
                lambda: db.table("feature_store").select("*").eq("entity_id", entity_id).execute()
            )
            
            # Default values
            features = {
                "entity_id": entity_id,
                "days_since_checkin": 0,
                "days_since_payment": 0,
                "message_response_time_avg": 0.0,
                "workout_completion_rate": 1.0,
                "weekly_weight_change": 0.0,
                "coach_response_time_avg": 0.0,
                "payment_retry_count": 0,
                "program_adherence_rate": 1.0
            }
            
            if feat_res.data:
                features = feat_res.data[0]

            # Recalculate based on current event
            if event_type == "payment_failed":
                features["payment_retry_count"] = features.get("payment_retry_count", 0) + 1
                features["days_since_payment"] = 0
            elif event_type == "payment_succeeded":
                features["payment_retry_count"] = 0
                features["days_since_payment"] = 0
            elif event_type == "checkin_completed":
                features["days_since_checkin"] = 0
                # Simulate workout completion / adherence updates
                features["program_adherence_rate"] = min(1.0, features.get("program_adherence_rate", 1.0) + 0.05)
            elif event_type == "workout_missed":
                features["program_adherence_rate"] = max(0.0, features.get("program_adherence_rate", 1.0) - 0.1)

            # Daily updates usually calculate "days_since..." but we mock the update logic here
            features["updated_at"] = datetime.utcnow().isoformat()
            
            await asyncio.to_thread(
                lambda: db.table("feature_store").upsert(features).execute()
            )
            
        except Exception as e:
            logger.error(f"Failed to update feature store for entity {entity_id}: {e}")

feature_store_service = FeatureStoreService()
