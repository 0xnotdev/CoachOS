import asyncio
from typing import Dict, Any, List
from app.services.supabase_client import supabase_service
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class SignalEngine:
    def __init__(self):
        self.db = None

    def _get_db(self):
        if not self.db:
            self.db = supabase_service.get_client()
        return self.db

    async def evaluate_signals(self, entity_id: str, coach_id: str):
        """
        Runs deterministic rule evaluations on features and state to extract composite signals.
        """
        db = self._get_db()
        try:
            # 1. Fetch current features & state in parallel
            feat_task = asyncio.to_thread(
                lambda: db.table("feature_store").select("*").eq("entity_id", entity_id).execute()
            )
            state_task = asyncio.to_thread(
                lambda: db.table("entity_state").select("last_checkin").eq("entity_id", entity_id).execute()
            )
            
            feat_res, state_res = await asyncio.gather(feat_task, state_task)
            
            if not feat_res.data:
                return

            features = feat_res.data[0]
            
            # Calculate days_since_checkin dynamically from state timestamp
            days_since_checkin = 999
            if state_res.data and state_res.data[0].get("last_checkin"):
                last_checkin_str = state_res.data[0]["last_checkin"]
                last_checkin = datetime.fromisoformat(last_checkin_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_since_checkin = max(0, (now - last_checkin).days)

            # Rule 1: Engagement Collapse
            if features.get("payment_retry_count", 0) > 1 and days_since_checkin > 7:
                await self._trigger_signal(
                    coach_id=coach_id,
                    entity_id=entity_id,
                    signal_type="engagement_collapse",
                    severity="high",
                    confidence=0.85,
                    evidence={
                        "payment_retry_count": features["payment_retry_count"], 
                        "days_since_checkin": days_since_checkin,
                        "amount": features.get("last_failed_payment_amount", 0.0)
                    }
                )

            # Rule 2: Transformation Stall
            if features.get("program_adherence_rate", 1.0) < 0.5:
                await self._trigger_signal(
                    coach_id=coach_id,
                    entity_id=entity_id,
                    signal_type="transformation_stall",
                    severity="medium",
                    confidence=0.75,
                    evidence={"program_adherence_rate": features["program_adherence_rate"]}
                )
                
        except Exception as e:
            logger.error(f"Failed signal evaluation for entity {entity_id}: {e}")

    async def resolve_signals_for_event(self, entity_id: str, event_type: str):
        """
        Resolves active signals when recovery events are received (e.g. payment succeeds).
        """
        db = self._get_db()
        try:
            if event_type == "payment_succeeded":
                await asyncio.to_thread(
                    lambda: db.table("signals")
                    .update({"status": "resolved"})
                    .eq("entity_id", entity_id)
                    .eq("signal_type", "engagement_collapse")
                    .eq("status", "active")
                    .execute()
                )
                logger.info(f"Resolved engagement_collapse signals for entity {entity_id}")
            elif event_type == "checkin_completed":
                await asyncio.to_thread(
                    lambda: db.table("signals")
                    .update({"status": "resolved"})
                    .eq("entity_id", entity_id)
                    .eq("signal_type", "transformation_stall")
                    .eq("status", "active")
                    .execute()
                )
                logger.info(f"Resolved transformation_stall signals for entity {entity_id}")
        except Exception as e:
            logger.error(f"Failed to resolve signals: {e}")

    async def _trigger_signal(self, coach_id: str, entity_id: str, signal_type: str, severity: str, confidence: float, evidence: Dict[str, Any]):
        db = self._get_db()
        try:
            # Deduplication: Checks for any active signal of this type without a 24-hour limit
            existing = await asyncio.to_thread(
                lambda: db.table("signals")
                .select("id")
                .eq("entity_id", entity_id)
                .eq("signal_type", signal_type)
                .eq("status", "active")
                .execute()
            )
            
            if not existing.data:
                await asyncio.to_thread(
                    lambda: db.table("signals").insert({
                        "coach_id": coach_id,
                        "entity_id": entity_id,
                        "signal_type": signal_type,
                        "severity": severity,
                        "confidence": confidence,
                        "status": "active",
                        "evidence": evidence
                    }).execute()
                )
                logger.info(f"Signal triggered: {signal_type} for entity {entity_id}")
        except Exception as e:
            logger.error(f"Failed to record signal: {e}")

# Global singleton
signal_engine = SignalEngine()
