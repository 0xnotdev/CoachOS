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
            
            # Fetch current features
            feat_res = await asyncio.to_thread(
                lambda: db.table("feature_store").select("*").eq("entity_id", entity_id).execute()
            )
            
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

            # Update features based on event type
            if event_type == "payment_failed":
                features["payment_retry_count"] = features.get("payment_retry_count", 0) + 1
                features["days_since_payment"] = 0
            elif event_type == "payment_succeeded":
                features["payment_retry_count"] = 0
                features["days_since_payment"] = 0
            elif event_type == "checkin_completed":
                features["days_since_checkin"] = 0
                # Exponential moving average for adherence
                features["program_adherence_rate"] = min(1.0, features.get("program_adherence_rate", 1.0) * 0.9 + 0.1)
            elif event_type == "workout_missed":
                features["program_adherence_rate"] = max(0.0, features.get("program_adherence_rate", 1.0) * 0.9)
            
            # Example calculation of weight changes if weight is passed in checkin payload
            if "weight" in payload:
                features["weekly_weight_change"] = payload["weight"] - features.get("weekly_weight_change", 0.0)

            features["updated_at"] = datetime.utcnow().isoformat()
            
            await asyncio.to_thread(
                lambda: db.table("feature_store").upsert(features).execute()
            )
            
        except Exception as e:
            logger.error(f"Failed to update feature store for entity {entity_id}: {e}")

    async def cron_recalculate_time_deltas(self):
        """
        Scheduled daily batch job that increments 'days_since_checkin' and 'days_since_payment'
        based on the last event timestamps stored in entity_state.
        """
        db = self._get_db()
        try:
            logger.info("Running daily feature store time-delta recalculation cron...")
            
            # Query all active states
            states = await asyncio.to_thread(
                lambda: db.table("entity_state").select("entity_id, last_checkin, last_payment").execute()
            )
            
            if not states.data:
                return

            now = datetime.utcnow()
            for row in states.data:
                entity_id = row["entity_id"]
                last_checkin_str = row.get("last_checkin")
                last_payment_str = row.get("last_payment")
                
                days_since_checkin = 999
                days_since_payment = 999
                
                if last_checkin_str:
                    last_checkin = datetime.fromisoformat(last_checkin_str.replace("Z", "+00:00"))
                    days_since_checkin = (now.date() - last_checkin.date()).days
                    
                if last_payment_str:
                    last_payment = datetime.fromisoformat(last_payment_str.replace("Z", "+00:00"))
                    days_since_payment = (now.date() - last_payment.date()).days

                # Upsert into Feature Store
                await asyncio.to_thread(
                    lambda: db.table("feature_store").upsert({
                        "entity_id": entity_id,
                        "days_since_checkin": max(0, days_since_checkin),
                        "days_since_payment": max(0, days_since_payment),
                        "updated_at": now.isoformat()
                    }).execute()
                )
            
            logger.info("Daily feature store time-delta recalculation completed.")
            
        except Exception as e:
            logger.error(f"Failed cron time-delta recalculation: {e}")

feature_store_service = FeatureStoreService()
