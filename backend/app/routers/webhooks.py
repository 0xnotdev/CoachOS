from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from app.integrations.stripe_adapter import stripe_adapter
from app.agents.orchestrator import intelligence_graph
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

def process_event_with_graph(event_data: dict):
    # This invokes the LangGraph DAG asynchronously/in the background
    initial_state = {
        "event": event_data,
        "revenue_context": "",
        "client_context": "",
        "program_context": "",
        "agent_outputs": [],
        "errors": []
    }
    result = intelligence_graph.invoke(initial_state)
    logger.info(f"Graph execution complete. Synthesis: {result.get('final_synthesis')}")

@router.post("/stripe")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing signature header")

    try:
        canonical_event = await stripe_adapter.handle_webhook(payload, sig_header)
        
        if canonical_event:
            # Trigger LangGraph
            background_tasks.add_task(process_event_with_graph, canonical_event.model_dump())
            logger.info(f"Successfully triggered graph for event: {canonical_event.event_type}")
            
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
        
    return {"status": "success"}
