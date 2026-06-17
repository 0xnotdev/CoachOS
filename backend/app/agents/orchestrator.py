import json
from typing import Dict, Any, TypedDict, List
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field
import logging
import litellm
from app.config import settings

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
    agent_outputs: List[Dict[str, Any]]
    final_synthesis: Dict[str, Any] | None

# Helper to call LLM
def ask_agent(system_prompt: str, user_prompt: str, response_format: type[BaseModel] | None = None) -> Any:
    # Uses LiteLLM to route to free Gemini tier
    # If no key, fallback to mock to prevent crashes locally if env is not set yet
    if not settings.GEMINI_API_KEY:
        logger.warning("No GEMINI_API_KEY found, returning mock response.")
        if response_format == SynthesisResult:
            return SynthesisResult(summary="Mock Synthesis", predictions=[], urgent_alerts=[]).model_dump()
        return AgentPrediction(domain="mock", prediction="Mock Prediction", confidence=1.0, recommended_action="None").model_dump()

    try:
        kwargs = {
            "model": "gemini/gemini-1.5-flash",
            "api_key": settings.GEMINI_API_KEY,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        }
        
        # We can use instructor or raw JSON mode depending on litellm support.
        # Since we want to ensure zero cost and no complex deps, we'll ask for JSON
        if response_format:
            kwargs["response_format"] = { "type": "json_object" }
            
        response = litellm.completion(**kwargs)
        content = response.choices[0].message.content
        
        if response_format:
            try:
                # Clean markdown backticks if any
                if content.startswith("```json"):
                    content = content[7:-3]
                return json.loads(content)
            except Exception as e:
                logger.error(f"Failed to parse JSON: {e}")
                return {}
        return content
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return {}

# --- Node Implementations ---
def revenue_agent_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Running Revenue Agent")
    event = state.get("event", {})
    
    sys_prompt = "You are the Revenue Intelligence Agent. Analyze the financial event and return a JSON matching: {'domain':'revenue', 'prediction':'...', 'confidence':0.9, 'recommended_action':'...'}"
    user_prompt = f"Event Data: {json.dumps(event)}"
    
    prediction = ask_agent(sys_prompt, user_prompt, AgentPrediction)
    
    output = {
        "domain": "revenue",
        "prediction": prediction
    }
    
    current_outputs = state.get("agent_outputs", [])
    current_outputs.append(output)
    return {"agent_outputs": current_outputs}

def client_agent_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Running Client Agent")
    event = state.get("event", {})
    
    sys_prompt = "You are the Client Intelligence Agent. Analyze the engagement event and return a JSON matching: {'domain':'engagement', 'prediction':'...', 'confidence':0.9, 'recommended_action':'...'}"
    user_prompt = f"Event Data: {json.dumps(event)}"
    
    prediction = ask_agent(sys_prompt, user_prompt, AgentPrediction)
    
    output = {
        "domain": "engagement",
        "prediction": prediction
    }
    current_outputs = state.get("agent_outputs", [])
    current_outputs.append(output)
    return {"agent_outputs": current_outputs}

def program_agent_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Running Program Agent")
    event = state.get("event", {})
    
    sys_prompt = "You are the Program Intelligence Agent. Analyze the compliance event and return a JSON matching: {'domain':'compliance', 'prediction':'...', 'confidence':0.9, 'recommended_action':'...'}"
    user_prompt = f"Event Data: {json.dumps(event)}"
    
    prediction = ask_agent(sys_prompt, user_prompt, AgentPrediction)
    
    output = {
        "domain": "compliance",
        "prediction": prediction
    }
    current_outputs = state.get("agent_outputs", [])
    current_outputs.append(output)
    return {"agent_outputs": current_outputs}

def synthesis_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Synthesizing Agent Outputs")
    outputs = state.get("agent_outputs", [])
    
    sys_prompt = "You are the AI Chief of Staff. Synthesize the sub-agent predictions into a daily briefing. Return JSON matching: {'summary':'...', 'predictions':[{...}], 'urgent_alerts':['...']}"
    user_prompt = f"Agent Predictions: {json.dumps(outputs)}"
    
    synthesis = ask_agent(sys_prompt, user_prompt, SynthesisResult)
    return {"final_synthesis": synthesis}

# --- Graph Definition ---
def build_orchestrator() -> StateGraph:
    workflow = StateGraph(GraphState)

    workflow.add_node("revenue_agent", revenue_agent_node)
    workflow.add_node("client_agent", client_agent_node)
    workflow.add_node("program_agent", program_agent_node)
    workflow.add_node("synthesis", synthesis_node)

    # Simple sequential flow for now
    workflow.set_entry_point("revenue_agent")
    workflow.add_edge("revenue_agent", "client_agent")
    workflow.add_edge("client_agent", "program_agent")
    workflow.add_edge("program_agent", "synthesis")
    workflow.add_edge("synthesis", END)

    return workflow.compile()

intelligence_graph = build_orchestrator()
