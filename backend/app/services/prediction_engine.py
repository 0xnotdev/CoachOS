import asyncio
from datetime import datetime
from typing import Dict, Any
from app.services.supabase_client import supabase_service
import math
import logging

logger = logging.getLogger(__name__)

class PredictionEngine:
    def __init__(self):
        self.db = None

    def _get_db(self):
        if not self.db:
            self.db = supabase_service.get_client()
        return self.db

    async def compute_predictions(self, entity_id: str):
        """
        Calculates churn probabilities using a smooth, continuous sigmoid formula.
        """
        db = self._get_db()
        try:
            # 1. Fetch features
            feat_res = await asyncio.to_thread(
                lambda: db.table("feature_store").select("*").eq("entity_id", entity_id).execute()
            )
            
            if not feat_res.data:
                return

            features = feat_res.data[0]

            # 2. Continuous Sigmoid Churn Scoring (no cliff effects)
            adherence = features.get("program_adherence_rate", 1.0)
            retries = features.get("payment_retry_count", 0)
            
            adherence_deficit = 1.0 - adherence
            payment_fatigue = 1.0 - (1.0 / (1.0 + retries))
            
            z = (adherence_deficit * 3.5) + (payment_fatigue * 4.0) - 2.5
            churn_prob = 1.0 / (1.0 + math.exp(-z))
            
            churn_prob = max(0.01, min(0.99, churn_prob))

            # 3. Upsert prediction with updated_at refresh
            now = datetime.utcnow().isoformat()
            await asyncio.to_thread(
                lambda: db.table("predictions").upsert({
                    "entity_id": entity_id,
                    "model_name": "churn_model",
                    "prediction_value": {"probability": churn_prob},
                    "updated_at": now
                }, on_conflict="entity_id,model_name").execute()
            )
            
            # Update entity_state
            await asyncio.to_thread(
                lambda: db.table("entity_state")
                .update({
                    "churn_probability": churn_prob,
                    "updated_at": now
                })
                .eq("entity_id", entity_id)
                .execute()
            )
            
            logger.info(f"Updated churn prediction for {entity_id}: Churn Risk {churn_prob:.2f} (smooth)")

        except Exception as e:
            logger.error(f"Failed prediction generation for entity {entity_id}: {e}")

prediction_engine = PredictionEngine()
