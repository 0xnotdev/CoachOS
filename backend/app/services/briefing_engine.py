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

    async def generate_daily_briefing(self, coach_id: str) -> str:
        """
        Gathers raw metrics, active signals, and proposed actions,
        and uses Gemini 1.5/2.5 Flash to synthesize a narrative daily briefing.
        """
        db = self._get_db()
        try:
            # 1. Fetch active signals for the coach's clients
            # (In production, join tables, here we query the coach_id column on signals)
            sig_res = await asyncio.to_thread(
                lambda: db.table("signals").select("*").eq("coach_id", coach_id).execute()
            )
            
            # 2. Fetch pending actions
            act_res = await asyncio.to_thread(
                lambda: db.table("actions").select("*").eq("coach_id", coach_id).eq("status", "suggested").execute()
            )

            signals = sig_res.data or []
            actions = act_res.data or []

            # 3. Compile context for LLM
            context = {
                "signals": [
                    {"type": s["signal_type"], "severity": s["severity"], "confidence": s["confidence"]}
                    for s in signals
                ],
                "recommended_actions": [
                    {"action": a["action_type"], "priority": a["priority"], "reason": a["reason"]}
                    for a in actions
                ]
            }

            if not signals and not actions:
                return "All clear! There are no urgent alerts, stalled transformations, or revenue risks today."

            # 4. Invoke LLM (Gemini) via LiteLLM
            if not settings.GEMINI_API_KEY:
                logger.warning("No GEMINI_API_KEY set. Returning structured JSON string as placeholder.")
                return f"Offline Mode Briefing: Detected {len(signals)} signals and {len(actions)} recommended actions."

            system_prompt = (
                "You are an expert AI Chief of Staff for fitness coaches. "
                "Synthesize the provided structured signals and recommended actions into a concise, professional, "
                "and highly actionable morning briefing. Highlight urgent items (revenue at risk, client churn risks, transformation stalls) "
                "clearly. Keep it motivating and brief."
            )
            
            user_prompt = f"Here is the daily data: {json.dumps(context)}"

            response = await asyncio.to_thread(
                lambda: litellm.completion(
                    model="gemini/gemini-1.5-flash",
                    api_key=settings.GEMINI_API_KEY,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
            )
            
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Failed to generate briefing: {e}")
            return "Failed to synthesize morning briefing due to an engine error."

briefing_engine = BriefingEngine()
