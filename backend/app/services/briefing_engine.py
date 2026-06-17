import asyncio
import json
from typing import Dict, Any, List
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from app.services.supabase_client import supabase_service
from app.config import settings
from datetime import datetime, timedelta, timezone
import litellm
import logging

logger = logging.getLogger(__name__)

# 1. Define LangGraph State Schema
class BriefingState(TypedDict):
    coach_id: str
    raw_signals: List[Dict[str, Any]]
    suggested_actions: List[Dict[str, Any]]
    persons_map: Dict[str, Dict[str, Any]]
    states_map: Dict[str, Dict[str, Any]]
    features_map: Dict[str, Dict[str, Any]]
    revenue_at_risk: float
    urgent_alerts: List[Dict[str, Any]]
    narrative: str

# 2. Define LangGraph Node Functions

async def gather_data_node(state: BriefingState) -> Dict[str, Any]:
    """
    Node 1: Gathers active signals, suggested actions, client profiles,
    and features from the database.
    """
    coach_id = state["coach_id"]
    db = supabase_service.get_client()

    # Fetch active signals and suggested actions in parallel
    sig_task = asyncio.to_thread(
        lambda: db.table("signals").select("*").eq("coach_id", coach_id).eq("status", "active").execute()
    )
    act_task = asyncio.to_thread(
        lambda: db.table("actions").select("*").eq("coach_id", coach_id).eq("status", "suggested").execute()
    )
    sig_res, act_res = await asyncio.gather(sig_task, act_task)
    
    signals = sig_res.data or []
    actions = act_res.data or []

    # Get distinct entity IDs involved in signals or actions
    entity_ids = list(set([s["entity_id"] for s in signals] + [a["entity_id"] for a in actions]))
    
    persons_map = {}
    states_map = {}
    features_map = {}
    
    if entity_ids:
        # Fetch profile data in parallel
        p_task = asyncio.to_thread(
            lambda: db.table("persons").select("id, name, email").in_("id", entity_ids).execute()
        )
        s_task = asyncio.to_thread(
            lambda: db.table("entity_state").select("*").in_("entity_id", entity_ids).execute()
        )
        f_task = asyncio.to_thread(
            lambda: db.table("feature_store").select("*").in_("entity_id", entity_ids).execute()
        )
        p_res, s_res, f_res = await asyncio.gather(p_task, s_task, f_task)
        
        persons_map = {row["id"]: row for row in (p_res.data or [])}
        states_map = {row["entity_id"]: row for row in (s_res.data or [])}
        features_map = {row["entity_id"]: row for row in (f_res.data or [])}

    return {
        "raw_signals": signals,
        "suggested_actions": actions,
        "persons_map": persons_map,
        "states_map": states_map,
        "features_map": features_map
    }

async def check_predictions_node(state: BriefingState) -> Dict[str, Any]:
    """
    Node 2: Scans client features and calculates revenue risk and prediction scores.
    """
    signals = state["raw_signals"]
    revenue_at_risk = 0.0

    for sig in signals:
        evidence = sig.get("evidence") or {}
        # Stripe webhooks store failed payment amount under 'amount'
        amount_failed = float(evidence.get("amount", 0.0))
        if sig["signal_type"] == "engagement_collapse":
            revenue_at_risk += amount_failed

    return {
        "revenue_at_risk": revenue_at_risk
    }

async def suggest_actions_node(state: BriefingState) -> Dict[str, Any]:
    """
    Node 3: Maps active signals to actions and builds prioritised alerts list.
    """
    signals = state["raw_signals"]
    actions = state["suggested_actions"]
    persons_map = state["persons_map"]
    
    urgent_alerts = []
    
    for sig in signals:
        eid = sig["entity_id"]
        sig_id = sig["id"]
        p_name = persons_map.get(eid, {}).get("name", "Unknown Client")
        
        # Match using signal_id link
        matching_action = next((a for a in actions if a.get("signal_id") == sig_id), None)
        urgent_alerts.append({
            "action_id": matching_action["id"] if matching_action else None,
            "client_name": p_name,
            "signal_type": sig["signal_type"],
            "severity": sig["severity"],
            "action_suggested": matching_action["action_type"] if matching_action else "Monitor client closely"
        })

    return {
        "urgent_alerts": urgent_alerts
    }

async def synthesize_briefing_node(state: BriefingState) -> Dict[str, Any]:
    """
    Node 4: Synthesizes rich gathered context into a professional morning briefing narrative.
    """
    signals = state["raw_signals"]
    actions = state["suggested_actions"]
    persons_map = state["persons_map"]
    states_map = state["states_map"]
    features_map = state["features_map"]
    
    rich_signals = []
    now = datetime.now(timezone.utc)
    
    for sig in signals:
        eid = sig["entity_id"]
        p_name = persons_map.get(eid, {}).get("name", "Unknown Client")
        p_email = persons_map.get(eid, {}).get("email", "")
        client_state = states_map.get(eid, {})
        features = features_map.get(eid, {})
        
        # Calculate days_since_checkin dynamically
        last_checkin_str = client_state.get("last_checkin")
        days_since_checkin = 999
        if last_checkin_str:
            last_checkin = datetime.fromisoformat(last_checkin_str.replace("Z", "+00:00"))
            days_since_checkin = max(0, (now - last_checkin).days)

        rich_signals.append({
            "client_name": p_name,
            "client_email": p_email,
            "signal_type": sig["signal_type"],
            "severity": sig["severity"],
            "confidence": sig["confidence"],
            "compliance_score": client_state.get("compliance_score", 100),
            "engagement_score": client_state.get("engagement_score", 100),
            "days_since_checkin": days_since_checkin,
            "payment_retry_count": features.get("payment_retry_count", 0),
        })

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
        
        try:
            response = await litellm.acompletion(
                model="gemini/gemini-1.5-flash",
                api_key=settings.GEMINI_API_KEY,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            narrative = response.choices[0].message.content
        except Exception as e:
            logger.error(f"LiteLLM invocation failed: {e}")
            narrative = "Morning briefing synthesis is currently offline due to an LLM service connection error."

    return {
        "narrative": narrative
    }

# 3. Assemble and Compile LangGraph State Graph
workflow = StateGraph(BriefingState)
workflow.add_node("gather_data", gather_data_node)
workflow.add_node("check_predictions", check_predictions_node)
workflow.add_node("suggest_actions", suggest_actions_node)
workflow.add_node("synthesize_briefing", synthesize_briefing_node)

workflow.add_edge(START, "gather_data")
workflow.add_edge("gather_data", "check_predictions")
workflow.add_edge("check_predictions", "suggest_actions")
workflow.add_edge("suggest_actions", "synthesize_briefing")
workflow.add_edge("synthesize_briefing", END)

briefing_graph = workflow.compile()

# 4. Briefing Engine Definition
class BriefingEngine:
    def __init__(self):
        self.db = None

    def _get_db(self):
        if not self.db:
            self.db = supabase_service.get_client()
        return self.db

    async def generate_daily_briefing(self, coach_id: str) -> Dict[str, Any]:
        """
        Uses LangGraph State Graph to gather metrics, analyze models, and synthesize
        daily client briefing narrative with 30-minute caching layer.
        """
        db = self._get_db()
        try:
            # 1. Check Cache Layer
            cache_res = await asyncio.to_thread(
                lambda: db.table("briefings")
                .select("generated_at, briefing_content")
                .eq("coach_id", coach_id)
                .execute()
            )
            
            if cache_res.data:
                cached = cache_res.data[0]
                generated_at = datetime.fromisoformat(cached["generated_at"].replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if now - generated_at < timedelta(minutes=30):
                    logger.info(f"Returning cached daily briefing for Coach {coach_id} (generated_at: {cached['generated_at']})")
                    return cached["briefing_content"]

            # Cache miss: Run Agentic LangGraph State Graph
            logger.info(f"Cache miss for Coach {coach_id}. Executing LangGraph synthesis pipeline...")
            
            initial_state: BriefingState = {
                "coach_id": coach_id,
                "raw_signals": [],
                "suggested_actions": [],
                "persons_map": {},
                "states_map": {},
                "features_map": {},
                "revenue_at_risk": 0.0,
                "urgent_alerts": [],
                "narrative": ""
            }

            final_state = await briefing_graph.ainvoke(initial_state)

            briefing_payload = {
                "briefing": final_state["narrative"],
                "urgent_alerts": final_state["urgent_alerts"],
                "revenue_at_risk": final_state["revenue_at_risk"],
                "active_signals_count": len(final_state["raw_signals"]),
                "pending_actions_count": len(final_state["suggested_actions"])
            }

            # Update cache table
            await asyncio.to_thread(
                lambda: db.table("briefings")
                .upsert({
                    "coach_id": coach_id,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "briefing_content": briefing_payload
                })
                .execute()
            )
            logger.info(f"Daily briefing cached successfully for Coach {coach_id}")

            return briefing_payload

        except Exception as e:
            logger.error(f"Failed to generate LangGraph daily briefing: {e}")
            return {
                "briefing": "Failed to synthesize morning briefing due to an internal server error.",
                "urgent_alerts": [],
                "revenue_at_risk": 0.0,
                "active_signals_count": 0,
                "pending_actions_count": 0
            }

briefing_engine = BriefingEngine()
