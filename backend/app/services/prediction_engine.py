import asyncio
from typing import Dict, Any
from app.services.supabase_client import supabase_service
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
        Runs ML models (XGBoost/LightGBM placeholders) on Feature Store values
        to generate probabilities for churn, upsell, expansion, etc.
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

            # 2. Mock Churn Prediction (normally XGBoost model inference)
            # High payment retries + low adherence increases churn risk
            adherence = features.get("program_adherence_rate", 1.0)
            retries = features.get("payment_retry_count", 0)
            
            base_churn = 0.05
            if adherence < 0.5:
                base_churn += 0.45
            if retries > 0:
                base_churn += 0.30
            
            churn_prob = min(0.99, base_churn)

            # Update predictions table
            await asyncio.to_thread(
                lambda: db.table("predictions").insert({
                    "entity_id": entity_id,
                    "model_name": "churn_model",
                    "prediction_value": {"probability": churn_prob}
                }).execute()
            )
            
            # Update entity_state with the computed probability
            await asyncio.to_thread(
                lambda: db.table("entity_state")
                .update({"churn_probability": churn_prob})
                .eq("entity_id", entity_id)
                .execute()
            )
            
            logger.info(f"Generated predictions for {entity_id}: Churn Risk {churn_prob:.2f}")

        except Exception as e:
            logger.error(f"Failed prediction generation for entity {entity_id}: {e}")

prediction_engine = PredictionEngine()
