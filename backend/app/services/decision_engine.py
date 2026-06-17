import asyncio
from typing import Dict, Any
from app.services.supabase_client import supabase_service
import logging

logger = logging.getLogger(__name__)

class DecisionEngine:
    def __init__(self):
        self.db = None

    def _get_db(self):
        if not self.db:
            self.db = supabase_service.get_client()
        return self.db

    async def evaluate_decisions(self, entity_id: str, coach_id: str):
        """
        Evaluates signals and predictions to output recommendations to the Action Graph.
        """
        db = self._get_db()
        try:
            # 1. Fetch active signals
            sig_res = await asyncio.to_thread(
                lambda: db.table("signals").select("*").eq("entity_id", entity_id).execute()
            )
            
            # 2. Fetch latest predictions
            pred_res = await asyncio.to_thread(
                lambda: db.table("predictions")
                .select("*")
                .eq("entity_id", entity_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            signals = sig_res.data or []
            prediction = pred_res.data[0] if pred_res.data else {}

            # Business Rules to generate Actions
            for sig in signals:
                sig_type = sig.get("signal_type")
                
                if sig_type == "engagement_collapse":
                    await self._recommend_action(
                        entity_id=entity_id,
                        coach_id=coach_id,
                        priority=90,
                        action_type="schedule_intervention_call",
                        reason={"signal": "engagement_collapse", "evidence": sig.get("evidence")}
                    )
                elif sig_type == "transformation_stall":
                    await self._recommend_action(
                        entity_id=entity_id,
                        coach_id=coach_id,
                        priority=60,
                        action_type="adjust_program_parameters",
                        reason={"signal": "transformation_stall", "evidence": sig.get("evidence")}
                    )

            # High churn probability rules
            prob = prediction.get("prediction_value", {}).get("probability", 0.0)
            if prob > 0.80:
                await self._recommend_action(
                    entity_id=entity_id,
                    coach_id=coach_id,
                    priority=95,
                    action_type="offer_subscription_modification",
                    reason={"prediction": "high_churn_risk", "probability": prob}
                )

        except Exception as e:
            logger.error(f"Failed decision analysis for entity {entity_id}: {e}")

    async def _recommend_action(self, entity_id: str, coach_id: str, priority: int, action_type: str, reason: Dict[str, Any]):
        db = self._get_db()
        try:
            # Check if action has already been suggested to avoid duplicate recommendations
            existing = await asyncio.to_thread(
                lambda: db.table("actions")
                .select("id")
                .eq("entity_id", entity_id)
                .eq("action_type", action_type)
                .eq("status", "suggested")
                .execute()
            )
            
            if not existing.data:
                await asyncio.to_thread(
                    lambda: db.table("actions").insert({
                        "entity_id": entity_id,
                        "coach_id": coach_id,
                        "priority": priority,
                        "action_type": action_type,
                        "reason": reason,
                        "status": "suggested"
                    }).execute()
                )
                logger.info(f"Recommended action logged: {action_type} for entity {entity_id}")
        except Exception as e:
            logger.error(f"Failed to record action recommendation: {e}")

decision_engine = DecisionEngine()
