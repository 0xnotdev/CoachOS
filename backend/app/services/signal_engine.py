import asyncio
from typing import Dict, Any, List
from app.services.supabase_client import supabase_service
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
        Runs deterministic rule evaluations on the Feature Store to extract composite signals.
        """
        db = self._get_db()
        try:
            # 1. Fetch current features
            feat_res = await asyncio.to_thread(
                lambda: db.table("feature_store").select("*").eq("entity_id", entity_id).execute()
            )
            
            if not feat_res.data:
                return

            features = feat_res.data[0]
            
            # Rule 1: Engagement Collapse
            # Late payment (payment retries > 1) + not checked in for > 7 days
            if features.get("payment_retry_count", 0) > 1 and features.get("days_since_checkin", 0) > 7:
                await self._trigger_signal(
                    coach_id=coach_id,
                    entity_id=entity_id,
                    signal_type="engagement_collapse",
                    severity="high",
                    confidence=0.85,
                    evidence={"payment_retry_count": features["payment_retry_count"], "days_since_checkin": features["days_since_checkin"]}
                )

            # Rule 2: Transformation Stall
            # Lower adherence rate (< 0.5) + flat weekly weight changes (example indicator)
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

    async def _trigger_signal(self, coach_id: str, entity_id: str, signal_type: str, severity: str, confidence: float, evidence: Dict[str, Any]):
        db = self._get_db()
        try:
            # Check if signal already exists/active in last 24h
            existing = await asyncio.to_thread(
                lambda: db.table("signals")
                .select("id")
                .eq("entity_id", entity_id)
                .eq("signal_type", signal_type)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            
            if not existing.data:
                # Trigger a new signal
                await asyncio.to_thread(
                    lambda: db.table("signals").insert({
                        "coach_id": coach_id,
                        "entity_id": entity_id,
                        "signal_type": signal_type,
                        "severity": severity,
                        "confidence": confidence,
                        "evidence": evidence
                    }).execute()
                )
                logger.info(f"Signal triggered: {signal_type} for entity {entity_id}")
        except Exception as e:
            logger.error(f"Failed to record signal: {e}")

signal_engine = SignalEngine()
