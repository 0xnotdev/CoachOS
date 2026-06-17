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
            payload = new_event.get("structured_payload") or {}
            coach_id = new_event.get("coach_id")
            
            # Resolve coach_id if not present directly in the event payload
            if not coach_id:
                client_res = await asyncio.to_thread(
                    lambda: db.table("clients")
                    .select("coach_id")
                    .eq("person_id", entity_id)
                    .execute()
                )
                if client_res.data:
                    coach_id = client_res.data[0]["coach_id"]

            feat_res = await asyncio.to_thread(
                lambda: db.table("feature_store").select("*").eq("entity_id", entity_id).execute()
            )
            
            features = {
                "entity_id": entity_id,
                "coach_id": str(coach_id) if coach_id else None,
                "message_response_time_avg": 0.0,
                "workout_completion_rate": 1.0,
                "weekly_weight_change": 0.0,
                "last_known_weight": None,
                "last_failed_payment_amount": 0.0,
                "coach_response_time_avg": 0.0,
                "payment_retry_count": 0,
                "program_adherence_rate": 1.0
            }
            
            if feat_res.data:
                features = feat_res.data[0]
                if coach_id:
                    features["coach_id"] = str(coach_id)

            if event_type == "payment_failed":
                features["payment_retry_count"] = features.get("payment_retry_count", 0) + 1
                features["last_failed_payment_amount"] = float(payload.get("amount", 0.0))
            elif event_type == "payment_succeeded":
                features["payment_retry_count"] = 0
                features["last_failed_payment_amount"] = 0.0
            elif event_type == "checkin_completed":
                features["program_adherence_rate"] = min(1.0, features.get("program_adherence_rate", 1.0) * 0.9 + 0.1)
            elif event_type == "workout_missed":
                features["program_adherence_rate"] = max(0.0, features.get("program_adherence_rate", 1.0) * 0.9)
            
            if "weight" in payload:
                new_weight = float(payload["weight"])
                last_weight = features.get("last_known_weight")
                
                if last_weight is not None:
                    features["weekly_weight_change"] = new_weight - float(last_weight)
                else:
                    features["weekly_weight_change"] = 0.0
                    
                features["last_known_weight"] = new_weight

            features["updated_at"] = datetime.utcnow().isoformat()
            
            await asyncio.to_thread(
                lambda: db.table("feature_store").upsert(features).execute()
            )
            
        except Exception as e:
            logger.error(f"Failed to update feature store for entity {entity_id}: {e}")

feature_store_service = FeatureStoreService()
