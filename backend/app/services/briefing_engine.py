import asyncio
import json
from typing import Dict, Any, List
from app.services.supabase_client import supabase_service
from app.config import settings
import litellm
import logging

logger = logging.getLogger(__name__)

class BriefingEngine:
    def __init__(self):
        self.db = None

    def _get_db(self):
        if not self.db:
            self.db = supabase_service.get_client()
        return self.db

    async def generate_daily_briefing(self, coach_id: str) -> Dict[str, Any]:
        """
        Gathers raw metrics, active signals, predictions, and proposed actions,
        and uses Gemini 1.5/2.5 Flash to synthesize a narrative daily briefing.
        """
        db = self._get_db()
        try:
            # 1. Fetch active signals
            sig_res = await asyncio.to_thread(
                lambda: db.table("signals")
                .select("*")
                .eq("coach_id", coach_id)
                .eq("status", "active")
                .execute()
            )
            signals = sig_res.data or []
            
            # 2. Fetch pending actions
            act_res = await asyncio.to_thread(
                lambda: db.table("actions")
                .select("*")
                .eq("coach_id", coach_id)
                .eq("status", "suggested")
                .execute()
            )
            actions = act_res.data or []

            # 3. Fetch auxiliary entities (persons, features, states) to build rich context
            entity_ids = list(set([s["entity_id"] for s in signals] + [a["entity_id"] for a in actions]))
            
            persons_map = {}
            states_map = {}
            features_map = {}
            
            if entity_ids:
                p_res = await asyncio.to_thread(
                    lambda: db.table("persons").select("id, name, email").in_("id", entity_ids).execute()
                )
                persons_map = {row["id"]: row for row in (p_res.data or [])}

                s_res = await asyncio.to_thread(
                    lambda: db.table("entity_state").select("*").in_("entity_id", entity_ids).execute()
                )
                states_map = {row["entity_id"]: row for row in (s_res.data or [])}

                f_res = await asyncio.to_thread(
                    lambda: db.table("feature_store").select("*").in_("entity_id", entity_ids).execute()
                )
                features_map = {row["entity_id"]: row for row in (f_res.data or [])}

            # 4. Compile rich context list for LLM prompt
            rich_signals = []
            revenue_at_risk = 0.0
            urgent_alerts = []

            for sig in signals:
                eid = sig["entity_id"]
                sig_id = sig["id"]
                p_name = persons_map.get(eid, {}).get("name", "Unknown Client")
                p_email = persons_map.get(eid, {}).get("email", "")
                state = states_map.get(eid, {})
                features = features_map.get(eid, {})
                
                # Retrieve the failed payment amount to compute accurate revenue at risk
                evidence = sig.get("evidence") or {}
                amount_failed = float(evidence.get("amount", 0.0))
                if sig["signal_type"] == "engagement_collapse":
                    revenue_at_risk += amount_failed

                rich_sig = {
                    "client_name": p_name,
                    "client_email": p_email,
                    "signal_type": sig["signal_type"],
                    "severity": sig["severity"],
                    "confidence": sig["confidence"],
                    "compliance_score": state.get("compliance_score", 100),
                    "engagement_score": state.get("engagement_score", 100),
                    "days_since_checkin": features.get("days_since_checkin", 0),
                    "payment_retry_count": features.get("payment_retry_count", 0),
                }
                rich_signals.append(rich_sig)
                
                # Pair accurately using signal_id link instead of generic positional entity matches
                matching_action = next((a for a in actions if a.get("signal_id") == sig_id), None)
                urgent_alerts.append({
                    "action_id": matching_action["id"] if matching_action else None,
                    "client_name": p_name,
                    "signal_type": sig["signal_type"],
                    "severity": sig["severity"],
                    "action_suggested": matching_action["action_type"] if matching_action else "Monitor client closely"
                })

            # Build narrative using async LiteLLM calls
            narrative = "All client parameters are stable. No active alerts or interventions required today."
            
            if rich_signals or actions:
                system_prompt = (
                    "You are an expert AI Chief of Staff for elite fitness coaches. "
                    "Analyze the provided structured client metrics, active alerts, and recommended actions. "
                    "Synthesize them into a highly professional, narrative daily morning briefing. "
                    "Refer to clients by their actual names. Highlight immediate priorities (revenue at risk, client compliance drops, transformation stalls) "
                    "clearly and explain WHY they require attention based on their data. Keep the tone sharp, motivating, and actionable."
                )
                
                user_prompt = f"Coach Business Daily Context:\n{json.dumps({'signals': rich_signals, 'suggested_actions': actions})}"
                
                response = await litellm.acompletion(
                    model="gemini/gemini-1.5-flash",
                    api_key=settings.GEMINI_API_KEY,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                narrative = response.choices[0].message.content

            return {
                "briefing": narrative,
                "urgent_alerts": urgent_alerts,
                "revenue_at_risk": revenue_at_risk,
                "active_signals_count": len(signals),
                "pending_actions_count": len(actions)
            }

        except Exception as e:
            logger.error(f"Failed to generate structured briefing: {e}")
            return {
                "briefing": "Failed to synthesize morning briefing due to an internal server error.",
                "urgent_alerts": [],
                "revenue_at_risk": 0.0,
                "active_signals_count": 0,
                "pending_actions_count": 0
            }

briefing_engine = BriefingEngine()
