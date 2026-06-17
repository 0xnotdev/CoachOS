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
                "last_known_weight": None,
                "coach_response_time_avg": 0.0,
                "payment_retry_count": 0,
                "program_adherence_rate": 1.0
            }
            
            if feat_res.data:
                features = feat_res.data[0]

            if event_type == "payment_failed":
                features["payment_retry_count"] = features.get("payment_retry_count", 0) + 1
                features["days_since_payment"] = 0
            elif event_type == "payment_succeeded":
                features["payment_retry_count"] = 0
                features["days_since_payment"] = 0
            elif event_type == "checkin_completed":
                features["days_since_checkin"] = 0
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

    def _upsert_features_batch(self, entity_id: str, days_since_checkin: int, days_since_payment: int, updated_at: str):
        db = self._get_db()
        db.table("feature_store").upsert({
            "entity_id": entity_id,
            "days_since_checkin": days_since_checkin,
            "days_since_payment": days_since_payment,
            "updated_at": updated_at
        }).execute()

    async def cron_recalculate_time_deltas(self):
        """
        Scheduled daily batch job that increments 'days_since_checkin' and 'days_since_payment'.
        Correctly paginates queries via .range() limit boundaries to scale past database defaults.
        """
        db = self._get_db()
        try:
            logger.info("Running daily feature store time-delta recalculation cron...")
            
            page_size = 100
            start = 0
            has_more = True
            now = datetime.utcnow()
            
            while has_more:
                end = start + page_size - 1
                logger.info(f"Fetching entity states in range {start} to {end}")
                
                states = await asyncio.to_thread(
                    lambda: db.table("entity_state")
                    .select("entity_id, last_checkin, last_payment")
                    .range(start, end)
                    .execute()
                )
                
                if not states.data:
                    break

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

                    await asyncio.to_thread(
                        self._upsert_features_batch,
                        entity_id,
                        max(0, days_since_checkin),
                        max(0, days_since_payment),
                        now.isoformat()
                    )
                
                if len(states.data) < page_size:
                    has_more = False
                else:
                    start += page_size
            
            logger.info("Daily feature store time-delta recalculation completed.")
            
        except Exception as e:
            logger.error(f"Failed cron time-delta recalculation: {e}")

feature_store_service = FeatureStoreService()
