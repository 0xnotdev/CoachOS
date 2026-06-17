from typing import Dict, Any, TypedDict, Annotated, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

# --- Pydantic Schemas for Structured Agent Output ---
class AgentPrediction(BaseModel):
    domain: str
    prediction: str
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_action: str

class SynthesisResult(BaseModel):
    summary: str
    predictions: List[AgentPrediction]
    urgent_alerts: List[str]

# --- State Definition ---
class GraphState(TypedDict):
    event: Dict[str, Any]
    revenue_context: str
    client_context: str
    program_context: str
    agent_outputs: List[Dict[str, Any]]
    final_synthesis: SynthesisResult | None
    errors: List[str]

# --- Node Implementations ---
def revenue_agent_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Running Revenue Agent")
    # In production, this would query Supabase for payment history and use an LLM
    # For now, we mock the logic to keep it lightweight
    event = state.get("event", {})
    output = {
        "domain": "revenue",
        "analysis": "Analyzed recent payment events.",
        "prediction": {"domain": "revenue", "prediction": "Stable MRR", "confidence": 0.85, "recommended_action": "None"}
    }
    return {"agent_outputs": [output]}

def client_agent_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Running Client Agent")
    # Mocked engagement analysis
    output = {
        "domain": "client_engagement",
        "analysis": "Analyzed recent check-ins and messages.",
        "prediction": {"domain": "engagement", "prediction": "High engagement", "confidence": 0.9, "recommended_action": "Praise client"}
    }
    return {"agent_outputs": [output]}

def program_agent_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Running Program Agent")
    # Mocked program compliance analysis
    output = {
        "domain": "program_compliance",
        "analysis": "Analyzed workout logs.",
        "prediction": {"domain": "compliance", "prediction": "On track", "confidence": 0.95, "recommended_action": "Increase weight"}
    }
    return {"agent_outputs": [output]}

def synthesis_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Synthesizing Agent Outputs")
    # Here we would use LiteLLM + Gemini 2.5 Flash with structured output to synthesize
    # the inputs from all 3 agents into a final brief.
    
    predictions = []
    for out in state.get("agent_outputs", []):
        pred = out.get("prediction")
        if pred:
            predictions.append(AgentPrediction(**pred))
            
    synthesis = SynthesisResult(
        summary="Processed all signals successfully.",
        predictions=predictions,
        urgent_alerts=[]
    )
    return {"final_synthesis": synthesis}

# --- Graph Definition ---
def build_orchestrator() -> StateGraph:
    # A StateGraph automatically merges dictionary returns into the State
    # Because agent_outputs is a list, we need to instruct LangGraph to append rather than overwrite if we run them in parallel
    # For simplicity, we'll redefine the state to handle merges, or just return them sequentially.
    
    workflow = StateGraph(GraphState)

    workflow.add_node("revenue_agent", revenue_agent_node)
    workflow.add_node("client_agent", client_agent_node)
    workflow.add_node("program_agent", program_agent_node)
    workflow.add_node("synthesis", synthesis_node)

    # Simple sequential flow for now (can be upgraded to parallel branches easily)
    workflow.set_entry_point("revenue_agent")
    workflow.add_edge("revenue_agent", "client_agent")
    workflow.add_edge("client_agent", "program_agent")
    workflow.add_edge("program_agent", "synthesis")
    workflow.add_edge("synthesis", END)

    return workflow.compile()

intelligence_graph = build_orchestrator()
